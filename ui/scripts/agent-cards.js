/* ==========================================================================
   Support Orchestrator — Agent Status Cards Component
   ========================================================================== */

(function () {
  'use strict';

  /* ======================================================================
     Card State
     ====================================================================== */
  var _refs = {};        // { agentId: { card, badge, task, progressFill, elapsed, room } }
  var _startTimes = {};  // { agentId: timestamp when status became working }
  var _deps = null;      // { EventBus, AppState, CONFIG }

  /* ======================================================================
     Status Label Map
     ====================================================================== */
  var STATUS_LABELS = {
    idle: 'Idle',
    working: 'Working',
    thinking: 'Working',
    done: 'Done',
    error: 'Error'
  };

  /* ======================================================================
     Helpers
     ====================================================================== */

  /** Format milliseconds as "0.0s" or "1m 02s" */
  function formatElapsed(ms) {
    if (ms <= 0) return '0.0s';
    var totalSec = ms / 1000;
    if (totalSec < 60) {
      return totalSec.toFixed(1) + 's';
    }
    var min = Math.floor(totalSec / 60);
    var sec = Math.floor(totalSec % 60);
    return min + 'm ' + (sec < 10 ? '0' : '') + sec + 's';
  }

  /** Normalise status — treat "thinking" as "working" for display */
  function normalizeStatus(status) {
    if (status === 'thinking') return 'working';
    return status || 'idle';
  }

  /* ======================================================================
     DOM Construction
     ====================================================================== */

  function createCard(agentId, agentCfg) {
    var card = document.createElement('div');
    card.className = 'agent-card agent-card--' + agentId;
    if (agentId === 'linear') {
      card.classList.add('agent-card--inactive');
    }

    /* --- Header row: icon + name | badge --- */
    var header = document.createElement('div');
    header.className = 'agent-card__header';

    var identity = document.createElement('div');
    identity.className = 'agent-card__identity';

    var icon = document.createElement('span');
    icon.className = 'agent-card__icon';
    icon.textContent = agentCfg.icon;

    var name = document.createElement('span');
    name.className = 'agent-card__name';
    name.textContent = agentCfg.displayName;

    identity.appendChild(icon);
    identity.appendChild(name);

    var badge = document.createElement('span');
    badge.className = 'agent-card__badge agent-card__badge--idle';
    badge.textContent = 'Idle';

    header.appendChild(identity);
    header.appendChild(badge);

    /* --- Domain subtitle --- */
    var domain = document.createElement('div');
    domain.className = 'agent-card__domain';
    domain.textContent = agentCfg.domain;

    /* --- Task text --- */
    var task = document.createElement('div');
    task.className = 'agent-card__task agent-card__task--idle';
    task.textContent = 'Idle \u2014 Awaiting tasks';

    /* --- Progress bar --- */
    var progress = document.createElement('div');
    progress.className = 'agent-card__progress';

    var progressFill = document.createElement('div');
    progressFill.className = 'agent-card__progress-fill';
    progress.appendChild(progressFill);

    /* --- Footer: elapsed time + room label --- */
    var footer = document.createElement('div');
    footer.className = 'agent-card__footer';

    var elapsed = document.createElement('span');
    elapsed.className = 'agent-card__elapsed';
    elapsed.textContent = '0.0s';

    var room = document.createElement('span');
    room.className = 'agent-card__room';
    room.textContent = agentCfg.roomLabel;

    footer.appendChild(elapsed);
    footer.appendChild(room);

    /* --- Assemble --- */
    card.appendChild(header);
    card.appendChild(domain);
    card.appendChild(task);
    card.appendChild(progress);
    card.appendChild(footer);

    /* Store refs for fast updates */
    _refs[agentId] = {
      card: card,
      badge: badge,
      task: task,
      progressFill: progressFill,
      elapsed: elapsed,
      room: room
    };

    return card;
  }

  /* ======================================================================
     Status Update
     ====================================================================== */

  function setStatus(agentId, status, taskDescription) {
    var ref = _refs[agentId];
    if (!ref) return;

    var display = normalizeStatus(status);

    /* --- Badge --- */
    ref.badge.className = 'agent-card__badge agent-card__badge--' + display;
    ref.badge.textContent = STATUS_LABELS[status] || 'Idle';

    /* --- Task text --- */
    if (display === 'idle') {
      ref.task.className = 'agent-card__task agent-card__task--idle';
      ref.task.textContent = 'Idle \u2014 Awaiting tasks';
    } else {
      ref.task.className = 'agent-card__task';
      ref.task.textContent = taskDescription || STATUS_LABELS[status] || '';
    }

    /* --- Progress bar --- */
    ref.progressFill.className = 'agent-card__progress-fill';
    if (display === 'working') {
      ref.progressFill.classList.add('agent-card__progress-fill--working');
    } else if (display === 'done') {
      ref.progressFill.classList.add('agent-card__progress-fill--done');
    } else if (display === 'error') {
      ref.progressFill.classList.add('agent-card__progress-fill--error');
    }

    /* --- Working glow --- */
    ref.card.classList.remove('agent-card--working-glow');
    if (display === 'working') {
      ref.card.classList.add('agent-card--working-glow');
    }

    /* --- Elapsed timer tracking --- */
    if (display === 'working') {
      if (!_startTimes[agentId]) {
        _startTimes[agentId] = Date.now();
      }
      ref.elapsed.classList.add('agent-card__elapsed--active');
    } else {
      /* Freeze timer display at final value when done */
      if (_startTimes[agentId] && (display === 'done' || display === 'error')) {
        var finalMs = Date.now() - _startTimes[agentId];
        ref.elapsed.textContent = formatElapsed(finalMs);
      }
      if (display === 'idle') {
        _startTimes[agentId] = null;
        ref.elapsed.textContent = '0.0s';
      }
      ref.elapsed.classList.remove('agent-card__elapsed--active');
    }

    /* --- Flash animation for done --- */
    if (display === 'done') {
      ref.card.classList.remove('agent-card--flash');
      /* Force reflow to re-trigger animation */
      void ref.card.offsetWidth;
      ref.card.classList.add('agent-card--flash');
    }

    /* --- Linear card activation --- */
    if (agentId === 'linear') {
      if (display !== 'idle') {
        ref.card.classList.remove('agent-card--inactive');
        ref.card.classList.add('agent-card--active');
      }
    }
  }

  /* ======================================================================
     Tick — Update Elapsed Timers for Active Agents
     ====================================================================== */

  function onTick() {
    var now = Date.now();
    var agentIds = Object.keys(_startTimes);
    for (var i = 0; i < agentIds.length; i++) {
      var id = agentIds[i];
      if (_startTimes[id] && _refs[id]) {
        var ms = now - _startTimes[id];
        _refs[id].elapsed.textContent = formatElapsed(ms);
      }
    }
  }

  /* ======================================================================
     Reset — Return All Cards to Idle
     ====================================================================== */

  function reset() {
    var agentIds = Object.keys(_refs);
    for (var i = 0; i < agentIds.length; i++) {
      var id = agentIds[i];
      _startTimes[id] = null;
      setStatus(id, 'idle', null);

      /* Reset linear to inactive */
      if (id === 'linear') {
        _refs[id].card.classList.add('agent-card--inactive');
        _refs[id].card.classList.remove('agent-card--active');
      }

      /* Remove flash class */
      _refs[id].card.classList.remove('agent-card--flash');
    }
  }

  /* ======================================================================
     Initialization
     ====================================================================== */

  function init(deps) {
    _deps = deps;
    var CONFIG = deps.CONFIG;
    var EventBus = deps.EventBus;

    var grid = document.getElementById('agent-cards-grid');
    if (!grid) {
      console.error('[AgentCards] #agent-cards-grid element not found');
      return;
    }

    /* Clear any existing content */
    grid.innerHTML = '';

    /* Create a card for each agent defined in CONFIG.AGENTS */
    var agentKeys = Object.keys(CONFIG.AGENTS);
    for (var i = 0; i < agentKeys.length; i++) {
      var agentId = agentKeys[i];
      var agentCfg = CONFIG.AGENTS[agentId];
      var cardEl = createCard(agentId, agentCfg);
      grid.appendChild(cardEl);
    }

    /* --- Wire EventBus listeners --- */

    /* agent:update events from DemoRunner / WS handler */
    EventBus.on('agent:update', function (data) {
      if (!data || !data.name) return;
      var agentState = deps.AppState.agents[data.name];
      var desc = agentState ? agentState.taskDescription : null;
      setStatus(data.name, data.status, desc);
    });

    /* demo:tick — update elapsed timers */
    EventBus.on('demo:tick', function () {
      onTick();
    });

    /* state:reset — reset all cards */
    EventBus.on('state:reset', function () {
      reset();
    });

    console.log('[AgentCards] Component initialized with ' + agentKeys.length + ' agents');
  }

  /* ======================================================================
     Register Component
     ====================================================================== */

  window.registerComponent('agentCards', function (deps) {
    init(deps);
  });

})();
