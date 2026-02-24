/* ==========================================================================
   Support Orchestrator — Main Application Module
   ========================================================================== */

(function () {
  'use strict';

  /* ======================================================================
     EventBus — lightweight pub/sub
     ====================================================================== */
  const EventBus = {
    _listeners: {},

    on(event, callback) {
      if (!this._listeners[event]) {
        this._listeners[event] = [];
      }
      this._listeners[event].push(callback);
      return () => this.off(event, callback);
    },

    emit(event, data) {
      const handlers = this._listeners[event];
      if (!handlers) return;
      for (let i = 0; i < handlers.length; i++) {
        try {
          handlers[i](data);
        } catch (err) {
          console.error(`[EventBus] Error in handler for "${event}":`, err);
        }
      }
    },

    off(event, callback) {
      if (!event) {
        this._listeners = {};
        return;
      }
      if (!callback) {
        delete this._listeners[event];
        return;
      }
      const handlers = this._listeners[event];
      if (!handlers) return;
      this._listeners[event] = handlers.filter(function (h) { return h !== callback; });
    }
  };

  /* ======================================================================
     AppState — single source of truth
     ====================================================================== */
  const AppState = {
    agents: {},
    messages: [],
    timelineEvents: [],
    connectionStatus: 'disconnected', // 'disconnected' | 'connected' | 'demo'
    currentPhase: 'idle',             // 'idle' | 'running' | 'complete'
    demoStartTime: null,
    elapsedMs: 0,

    init() {
      const agentKeys = Object.keys(CONFIG.AGENTS);
      for (let i = 0; i < agentKeys.length; i++) {
        var key = agentKeys[i];
        this.agents[key] = {
          name: key,
          status: 'idle',       // 'idle' | 'working' | 'thinking' | 'done' | 'error'
          lastActivity: null,
          taskDescription: null
        };
      }
    },

    reset() {
      this.messages = [];
      this.timelineEvents = [];
      this.currentPhase = 'idle';
      this.demoStartTime = null;
      this.elapsedMs = 0;
      var agentKeys = Object.keys(this.agents);
      for (var i = 0; i < agentKeys.length; i++) {
        var key = agentKeys[i];
        this.agents[key].status = 'idle';
        this.agents[key].lastActivity = null;
        this.agents[key].taskDescription = null;
      }
    },

    setAgentStatus(agentName, status, description) {
      if (!this.agents[agentName]) return;
      this.agents[agentName].status = status;
      this.agents[agentName].lastActivity = Date.now();
      if (description !== undefined) {
        this.agents[agentName].taskDescription = description;
      }
    },

    addMessage(msg) {
      var message = Object.assign({}, msg, {
        id: 'msg-' + Date.now() + '-' + Math.random().toString(36).substring(2, 8),
        timestamp: Date.now()
      });
      this.messages.push(message);
      return message;
    },

    addTimelineEvent(evt) {
      var event = Object.assign({}, evt, {
        id: 'evt-' + Date.now() + '-' + Math.random().toString(36).substring(2, 8),
        timestamp: Date.now(),
        offsetMs: this.demoStartTime ? Date.now() - this.demoStartTime : 0
      });
      this.timelineEvents.push(event);
      return event;
    },

    getActiveAgentCount() {
      var count = 0;
      var agentKeys = Object.keys(this.agents);
      for (var i = 0; i < agentKeys.length; i++) {
        var status = this.agents[agentKeys[i]].status;
        if (status === 'working' || status === 'thinking') {
          count++;
        }
      }
      return count;
    }
  };

  /* ======================================================================
     WebSocket Connection Manager
     ====================================================================== */
  const ConnectionManager = {
    _ws: null,
    _reconnectAttempts: 0,
    _reconnectTimer: null,
    _heartbeatTimer: null,

    connect() {
      if (this._ws && (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)) {
        return;
      }

      try {
        this._ws = new WebSocket(CONFIG.WS_URL);
      } catch (err) {
        console.warn('[WS] Failed to create WebSocket:', err.message);
        this._scheduleReconnect();
        return;
      }

      this._ws.onopen = function () {
        console.log('[WS] Connected to', CONFIG.WS_URL);
        ConnectionManager._reconnectAttempts = 0;
        AppState.connectionStatus = 'connected';
        EventBus.emit('connection:change', 'connected');
        ConnectionManager._startHeartbeat();
      };

      this._ws.onmessage = function (event) {
        var data;
        try {
          data = JSON.parse(event.data);
        } catch (err) {
          console.warn('[WS] Non-JSON message received:', event.data);
          return;
        }
        EventBus.emit('ws:message', data);
      };

      this._ws.onclose = function (event) {
        console.log('[WS] Disconnected (code=' + event.code + ')');
        ConnectionManager._stopHeartbeat();
        if (AppState.connectionStatus !== 'demo') {
          AppState.connectionStatus = 'disconnected';
          EventBus.emit('connection:change', 'disconnected');
        }
        ConnectionManager._scheduleReconnect();
      };

      this._ws.onerror = function () {
        console.warn('[WS] Connection error');
      };
    },

    disconnect() {
      clearTimeout(this._reconnectTimer);
      this._stopHeartbeat();
      if (this._ws) {
        this._ws.onclose = null;
        this._ws.close();
        this._ws = null;
      }
    },

    send(data) {
      if (this._ws && this._ws.readyState === WebSocket.OPEN) {
        this._ws.send(JSON.stringify(data));
      }
    },

    _scheduleReconnect() {
      var delay = Math.min(
        CONFIG.TIMING.RECONNECT_DELAY * Math.pow(1.5, this._reconnectAttempts),
        CONFIG.TIMING.RECONNECT_MAX_DELAY
      );
      this._reconnectAttempts++;
      console.log('[WS] Reconnecting in ' + Math.round(delay / 1000) + 's (attempt ' + this._reconnectAttempts + ')');
      this._reconnectTimer = setTimeout(function () {
        ConnectionManager.connect();
      }, delay);
    },

    _startHeartbeat() {
      this._stopHeartbeat();
      this._heartbeatTimer = setInterval(function () {
        ConnectionManager.send({ type: 'ping' });
      }, CONFIG.TIMING.HEARTBEAT_INTERVAL);
    },

    _stopHeartbeat() {
      clearInterval(this._heartbeatTimer);
    }
  };

  /* ======================================================================
     DemoRunner — plays scenario events using setTimeout
     ====================================================================== */
  const DemoRunner = {
    _timers: [],
    _tickTimer: null,

    start(scenarioId) {
      var scenario = CONFIG.DEMO_SCENARIOS[scenarioId || 'branchA'];
      if (!scenario) {
        console.error('[DemoRunner] Scenario not found:', scenarioId);
        return;
      }

      this.stop();
      AppState.reset();
      EventBus.emit('state:reset');

      AppState.currentPhase = 'running';
      AppState.connectionStatus = 'demo';
      AppState.demoStartTime = Date.now();
      EventBus.emit('connection:change', 'demo');
      EventBus.emit('demo:start', scenario);

      var multiplier = CONFIG.TIMING.DEMO_SPEED_MULTIPLIER;
      var events = scenario.events;

      for (var i = 0; i < events.length; i++) {
        (function (evt) {
          var delay = evt.t * multiplier;
          var timer = setTimeout(function () {
            DemoRunner._processEvent(evt);
          }, delay);
          DemoRunner._timers.push(timer);
        })(events[i]);
      }

      /* Elapsed-time tick */
      this._tickTimer = setInterval(function () {
        if (AppState.demoStartTime) {
          AppState.elapsedMs = Date.now() - AppState.demoStartTime;
          EventBus.emit('demo:tick', AppState.elapsedMs);
        }
      }, CONFIG.TIMING.TIMELINE_TICK_MS);

      /* Schedule end after last event + small buffer */
      var lastT = events[events.length - 1].t;
      var endTimer = setTimeout(function () {
        DemoRunner._finish();
      }, (lastT + 1500) * multiplier);
      this._timers.push(endTimer);
    },

    stop() {
      for (var i = 0; i < this._timers.length; i++) {
        clearTimeout(this._timers[i]);
      }
      this._timers = [];
      clearInterval(this._tickTimer);
      this._tickTimer = null;
    },

    _processEvent(evt) {
      switch (evt.type) {

        case 'user_message':
          AppState.setAgentStatus('user', 'working', 'Sending support request');
          AppState.setAgentStatus('orchestrator', 'working', 'Receiving customer message');
          var userMsg = AppState.addMessage({
            type: 'user_message',
            from: evt.from,
            to: evt.to,
            text: evt.payload.text
          });
          AppState.addTimelineEvent({
            type: 'user_message',
            agent: 'user',
            label: 'Customer message received'
          });
          EventBus.emit('message:new', userMsg);
          EventBus.emit('agent:update', { name: 'user', status: 'working' });
          EventBus.emit('agent:update', { name: 'orchestrator', status: 'working' });
          EventBus.emit('phase:change', { label: 'Phase 1: Acknowledge' });
          break;

        case 'agent_status':
          AppState.setAgentStatus(evt.agent, evt.status, evt.payload.text);
          var statusMsg = AppState.addMessage({
            type: 'status',
            from: evt.agent,
            text: evt.payload.text,
            status: evt.status
          });
          AppState.addTimelineEvent({
            type: 'agent_status',
            agent: evt.agent,
            status: evt.status,
            label: CONFIG.AGENTS[evt.agent].displayName + ' \u2014 ' + evt.status
          });
          EventBus.emit('message:new', statusMsg);
          EventBus.emit('agent:update', { name: evt.agent, status: evt.status });
          if (evt.phase === 'synthesize') {
            EventBus.emit('phase:change', { label: 'Phase 3: Synthesize' });
          }
          break;

        case 'dispatch':
          AppState.setAgentStatus('orchestrator', 'working', evt.payload.text);
          var targets = evt.targets;
          for (var i = 0; i < targets.length; i++) {
            AppState.setAgentStatus(targets[i], 'idle', evt.payload.tasks[targets[i]]);
          }
          var dispatchMsg = AppState.addMessage({
            type: 'dispatch',
            from: evt.from,
            targets: targets,
            text: evt.payload.text,
            tasks: evt.payload.tasks
          });
          AppState.addTimelineEvent({
            type: 'dispatch',
            agent: 'orchestrator',
            targets: targets,
            label: 'Dispatched to ' + targets.join(', ')
          });
          EventBus.emit('message:new', dispatchMsg);
          EventBus.emit('agent:update', { name: 'orchestrator', status: 'working' });
          for (var j = 0; j < targets.length; j++) {
            EventBus.emit('topology:dispatch', { from: 'orchestrator', to: targets[j] });
          }
          EventBus.emit('phase:change', { label: 'Phase 2: Investigate' });
          break;

        case 'agent_result':
          AppState.setAgentStatus(evt.agent, evt.status, evt.payload.text);
          var resultMsg = AppState.addMessage({
            type: 'result',
            from: evt.agent,
            to: 'orchestrator',
            text: evt.payload.text
          });
          AppState.addTimelineEvent({
            type: 'agent_result',
            agent: evt.agent,
            label: CONFIG.AGENTS[evt.agent].displayName + ' completed'
          });
          EventBus.emit('message:new', resultMsg);
          EventBus.emit('agent:update', { name: evt.agent, status: 'done' });
          EventBus.emit('topology:result', { from: evt.agent, to: 'orchestrator' });
          break;

        case 'final_response':
          AppState.setAgentStatus('orchestrator', 'done', 'Response delivered');
          AppState.setAgentStatus('user', 'done', 'Response received');
          var finalMsg = AppState.addMessage({
            type: 'final_response',
            from: evt.from,
            to: evt.to,
            text: evt.payload.text
          });
          AppState.addTimelineEvent({
            type: 'final_response',
            agent: 'orchestrator',
            label: 'Final response sent to customer'
          });
          EventBus.emit('message:new', finalMsg);
          EventBus.emit('agent:update', { name: 'orchestrator', status: 'done' });
          EventBus.emit('agent:update', { name: 'user', status: 'done' });
          break;

        default:
          console.warn('[DemoRunner] Unknown event type:', evt.type);
      }

      EventBus.emit('state:updated');
    },

    _finish() {
      clearInterval(DemoRunner._tickTimer);
      DemoRunner._tickTimer = null;
      AppState.currentPhase = 'complete';
      AppState.elapsedMs = Date.now() - AppState.demoStartTime;
      EventBus.emit('demo:tick', AppState.elapsedMs);
      EventBus.emit('demo:complete', {
        elapsedMs: AppState.elapsedMs,
        messageCount: AppState.messages.length
      });
    }
  };

  /* ======================================================================
     Component Registry
     ====================================================================== */
  /* Import any components registered before app.js loaded (via the stub in config.js) */
  var _components = {};
  if (window._earlyComponents) {
    var earlyKeys = Object.keys(window._earlyComponents);
    for (var _e = 0; _e < earlyKeys.length; _e++) {
      _components[earlyKeys[_e]] = window._earlyComponents[earlyKeys[_e]];
    }
    delete window._earlyComponents;
  }

  window.registerComponent = function (name, initFn) {
    _components[name] = initFn;
  };

  function initAllComponents() {
    var names = Object.keys(_components);
    for (var i = 0; i < names.length; i++) {
      try {
        _components[names[i]]({ EventBus: EventBus, AppState: AppState, CONFIG: CONFIG });
        console.log('[App] Component initialized:', names[i]);
      } catch (err) {
        console.error('[App] Failed to initialize component "' + names[i] + '":', err);
      }
    }
  }

  /* ======================================================================
     UI Helpers
     ====================================================================== */
  function updateConnectionUI(status) {
    var el = document.getElementById('connection-status');
    if (!el) return;
    var dot = el.querySelector('.status-dot');
    var label = el.querySelector('.status-label');

    dot.className = 'status-dot';
    switch (status) {
      case 'connected':
        dot.classList.add('status-dot--connected');
        label.textContent = 'Connected';
        break;
      case 'demo':
        dot.classList.add('status-dot--demo');
        label.textContent = 'Demo Mode';
        break;
      default:
        dot.classList.add('status-dot--disconnected');
        label.textContent = 'Disconnected';
    }
  }

  function updateActiveAgentsCount() {
    var el = document.getElementById('active-agents-count');
    if (!el) return;
    var count = AppState.getActiveAgentCount();
    el.textContent = count + ' active';
  }

  function updateMessageCount() {
    var el = document.getElementById('message-count');
    if (!el) return;
    el.textContent = AppState.messages.length + ' messages';
  }

  function updateElapsedTime(ms) {
    var el = document.getElementById('elapsed-time');
    if (!el) return;
    el.textContent = (ms / 1000).toFixed(1) + 's';
  }

  /* ======================================================================
     Bootstrap
     ====================================================================== */
  document.addEventListener('DOMContentLoaded', function () {

    /* Initialize state */
    AppState.init();

    /* Dismiss loading screen */
    var loadingScreen = document.getElementById('loading-screen');
    var appShell = document.getElementById('app');

    setTimeout(function () {
      if (loadingScreen) {
        loadingScreen.classList.add('fade-out');
        loadingScreen.addEventListener('animationend', function () {
          loadingScreen.remove();
        });
      }
      if (appShell) {
        appShell.classList.remove('hidden');
      }
    }, CONFIG.TIMING.LOADING_SCREEN_MS);

    /* Initialize all registered components */
    initAllComponents();

    /* Wire up core event listeners */
    EventBus.on('connection:change', updateConnectionUI);
    EventBus.on('state:updated', updateActiveAgentsCount);
    EventBus.on('state:updated', updateMessageCount);
    EventBus.on('demo:tick', updateElapsedTime);

    /* ==================================================================
       Live event handler — process WebSocket messages from the bridge
       ================================================================== */
    EventBus.on('ws:message', function (data) {
      if (!data || !data.type) return;

      switch (data.type) {

        /* ---- Bridge status updates ---- */
        case 'bridge_status': {
          var status = data.status;
          if (status === 'connected' || status === 'live') {
            AppState.connectionStatus = 'connected';
            EventBus.emit('connection:change', 'connected');
          } else if (status === 'demo' || status === 'demo_available') {
            if (AppState.connectionStatus !== 'demo') {
              AppState.connectionStatus = 'connected';
              EventBus.emit('connection:change', 'connected');
            }
          }
          break;
        }

        /* ---- Raw Thenvoi room messages ---- */
        case 'message': {
          var agentKey = CONFIG.AGENT_NAME_MAP[data.sender] || null;
          if (!agentKey) break;
          var msg = AppState.addMessage({
            type: 'status',
            from: agentKey,
            text: data.content,
            room: data.room
          });
          EventBus.emit('message:new', msg);
          break;
        }

        /* ---- Parsed protocol agent_status (from bridge) ---- */
        case 'agent_status': {
          var agent = data.agent;
          if (!AppState.agents[agent]) break;
          AppState.setAgentStatus(agent, data.status, data.task);
          EventBus.emit('agent:update', { name: agent, status: data.status });
          if (data.status === 'working') {
            EventBus.emit('topology:dispatch', { from: 'orchestrator', to: agent });
          } else if (data.status === 'done') {
            EventBus.emit('topology:result', { from: agent, to: 'orchestrator' });
          }
          EventBus.emit('state:updated');
          break;
        }

        /* ---- Bridge demo lifecycle ---- */
        case 'demo_started': {
          AppState.reset();
          EventBus.emit('state:reset');
          AppState.currentPhase = 'running';
          AppState.connectionStatus = 'demo';
          AppState.demoStartTime = Date.now();
          EventBus.emit('connection:change', 'demo');
          EventBus.emit('demo:start', { id: data.scenario || 'branchA' });
          /* Start tick timer for elapsed time */
          if (DemoRunner._tickTimer) clearInterval(DemoRunner._tickTimer);
          DemoRunner._tickTimer = setInterval(function () {
            if (AppState.demoStartTime) {
              AppState.elapsedMs = Date.now() - AppState.demoStartTime;
              EventBus.emit('demo:tick', AppState.elapsedMs);
            }
          }, CONFIG.TIMING.TIMELINE_TICK_MS);
          break;
        }

        case 'demo_complete': {
          if (DemoRunner._tickTimer) {
            clearInterval(DemoRunner._tickTimer);
            DemoRunner._tickTimer = null;
          }
          AppState.currentPhase = 'complete';
          if (AppState.demoStartTime) {
            AppState.elapsedMs = Date.now() - AppState.demoStartTime;
          }
          EventBus.emit('demo:tick', AppState.elapsedMs);
          EventBus.emit('demo:complete', {
            elapsedMs: AppState.elapsedMs,
            messageCount: AppState.messages.length
          });
          break;
        }

        /* ---- Bridge demo events (match DemoRunner scenario format) ---- */
        case 'user_message':
        case 'dispatch':
        case 'agent_result':
        case 'final_response':
          DemoRunner._processEvent(data);
          break;
      }
    });

    /* Wire "Run Demo" button */
    var btnRunDemo = document.getElementById('btn-run-demo');
    if (btnRunDemo) {
      btnRunDemo.addEventListener('click', function () {
        if (AppState.currentPhase === 'running') return;
        btnRunDemo.disabled = true;
        /* If connected to the bridge, ask it to run the demo server-side */
        if (AppState.connectionStatus === 'connected') {
          ConnectionManager.send({ action: 'start_demo' });
        } else {
          /* Fallback to client-side demo */
          DemoRunner.start('branchA');
        }
      });
    }

    /* Wire "Reset" button */
    var btnReset = document.getElementById('btn-reset');
    if (btnReset) {
      btnReset.addEventListener('click', function () {
        DemoRunner.stop();
        AppState.reset();
        AppState.connectionStatus = 'disconnected';
        EventBus.emit('connection:change', 'disconnected');
        EventBus.emit('state:reset');
        EventBus.emit('state:updated');
        updateElapsedTime(0);
        if (btnRunDemo) btnRunDemo.disabled = false;
      });
    }

    /* Re-enable Run Demo button when demo completes */
    EventBus.on('demo:complete', function () {
      if (btnRunDemo) btnRunDemo.disabled = false;
    });

    /* Attempt WebSocket connection (non-blocking, will silently retry) */
    ConnectionManager.connect();

    /* Expose for debugging */
    window.__app = {
      EventBus: EventBus,
      AppState: AppState,
      DemoRunner: DemoRunner,
      ConnectionManager: ConnectionManager
    };

    console.log('[App] Support Orchestrator UI initialized');
  });

})();
