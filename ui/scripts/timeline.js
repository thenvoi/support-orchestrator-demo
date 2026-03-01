/* ==========================================================================
   Support Orchestrator — Horizontal Swim-Lane Timeline Component
   ========================================================================== */

window.registerComponent('timeline', function (deps) {
  'use strict';

  var EventBus = deps.EventBus;
  var AppState = deps.AppState;
  var CONFIG   = deps.CONFIG;

  /* ---- Constants ---- */
  var PX_PER_SECOND  = 80;
  var LANE_HEIGHT    = 32;
  var SIDEBAR_WIDTH  = 140;
  var TICK_SPACING   = PX_PER_SECOND; /* 1 tick mark per second */
  var TIME_AXIS_H    = 22;
  var BAR_V_PAD      = 4;
  var BAR_HEIGHT     = LANE_HEIGHT - BAR_V_PAD * 2;
  var LANE_BG_EVEN   = '#0d1220';
  var LANE_BG_ODD    = '#0f1428';

  /* Agent ordering (top to bottom) */
  var LANE_ORDER = ['user', 'orchestrator', 'excel', 'github', 'browser', 'linear'];

  /* ---- State ---- */
  var _startTime   = null;
  var _activeBars  = {};   /* agentId -> { el, startMs, label } */
  var _allBars     = [];   /* { el, agentId, startMs, endMs } */
  var _phases      = [];   /* { el, label, offsetMs } */
  var _nowCursor   = null;
  var _scrollArea  = null;
  var _canvasInner = null;
  var _axisRow     = null;
  var _laneEls     = {};   /* agentId -> lane row element */

  /* ---- DOM references ---- */
  var _root        = null; /* the .tl-root wrapper we create */

  /* ======================================================================
     DOM Construction
     ====================================================================== */
  function buildDOM() {
    var track = document.getElementById('timeline-track');
    if (!track) return;

    /* Clear any existing content */
    track.innerHTML = '';

    /* Root container — flex row: sidebar | scroll area */
    _root = el('div', 'tl-root');

    /* ---------- Fixed sidebar ---------- */
    var sidebar = el('div', 'tl-sidebar');

    /* Blank cell above sidebar to align with time axis */
    var sidebarAxisSpacer = el('div', 'tl-sidebar-spacer');
    sidebarAxisSpacer.style.height = TIME_AXIS_H + 'px';
    sidebar.appendChild(sidebarAxisSpacer);

    for (var i = 0; i < LANE_ORDER.length; i++) {
      var agentId = LANE_ORDER[i];
      var agentCfg = CONFIG.AGENTS[agentId];
      var nameCell = el('div', 'tl-sidebar-name');
      nameCell.style.height = LANE_HEIGHT + 'px';
      nameCell.style.color = agentCfg.color;
      nameCell.textContent = agentCfg.displayName;
      sidebar.appendChild(nameCell);
    }

    /* ---------- Scrollable area ---------- */
    _scrollArea = el('div', 'tl-scroll-area');

    /* Inner container — grows as time progresses */
    _canvasInner = el('div', 'tl-canvas-inner');

    /* Time axis row */
    _axisRow = el('div', 'tl-axis-row');
    _axisRow.style.height = TIME_AXIS_H + 'px';
    _canvasInner.appendChild(_axisRow);

    /* Swim lanes */
    for (var j = 0; j < LANE_ORDER.length; j++) {
      var laneId = LANE_ORDER[j];
      var lane = el('div', 'tl-lane');
      lane.style.height = LANE_HEIGHT + 'px';
      lane.style.background = (j % 2 === 0) ? LANE_BG_EVEN : LANE_BG_ODD;
      lane.setAttribute('data-agent', laneId);
      _laneEls[laneId] = lane;
      _canvasInner.appendChild(lane);
    }

    /* "Now" cursor */
    _nowCursor = el('div', 'tl-now-cursor');
    _nowCursor.style.top = '0';
    _nowCursor.style.height = (TIME_AXIS_H + LANE_ORDER.length * LANE_HEIGHT) + 'px';
    _canvasInner.appendChild(_nowCursor);

    _scrollArea.appendChild(_canvasInner);
    _root.appendChild(sidebar);
    _root.appendChild(_scrollArea);
    track.appendChild(_root);

    /* Set initial width */
    setCanvasWidth(0);
  }

  /* ======================================================================
     Helper: create element with class
     ====================================================================== */
  function el(tag, className) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    return e;
  }

  /* ======================================================================
     Canvas width management
     ====================================================================== */
  function setCanvasWidth(elapsedMs) {
    var seconds = elapsedMs / 1000;
    /* Always show at least the visible scroll area width, or the elapsed time + buffer */
    var minWidthPx = _scrollArea ? _scrollArea.clientWidth : 600;
    var timePx = (seconds + 2) * PX_PER_SECOND;
    var width = Math.max(minWidthPx, timePx);
    _canvasInner.style.width = width + 'px';
  }

  /* ======================================================================
     Time Axis Ticks
     ====================================================================== */
  function updateAxis(elapsedMs) {
    var totalSeconds = Math.ceil(elapsedMs / 1000) + 2;

    /* Only add ticks we haven't drawn yet */
    var existingCount = _axisRow.childElementCount;
    for (var s = existingCount; s <= totalSeconds; s++) {
      var tick = el('div', 'tl-axis-tick');
      tick.style.left = (s * TICK_SPACING) + 'px';

      var label = el('span', 'tl-axis-label');
      label.textContent = s + 's';
      tick.appendChild(label);

      _axisRow.appendChild(tick);
    }
  }

  /* ======================================================================
     Now Cursor
     ====================================================================== */
  function updateNowCursor(elapsedMs) {
    if (!_nowCursor) return;
    var x = (elapsedMs / 1000) * PX_PER_SECOND;
    _nowCursor.style.left = x + 'px';
  }

  /* ======================================================================
     Auto-scroll
     ====================================================================== */
  function autoScroll(elapsedMs) {
    if (!_scrollArea) return;
    var x = (elapsedMs / 1000) * PX_PER_SECOND;
    var visibleWidth = _scrollArea.clientWidth;
    /* Keep the now-cursor at ~75% from the left */
    var target = x - visibleWidth * 0.75;
    if (target > 0) {
      _scrollArea.scrollLeft = target;
    }
  }

  /* ======================================================================
     Activity Bars
     ====================================================================== */
  function msToX(ms) {
    return (ms / 1000) * PX_PER_SECOND;
  }

  function startTask(agentId, taskLabel) {
    if (!_laneEls[agentId]) return;

    /* If there's already an active bar for this agent, end it first */
    if (_activeBars[agentId]) {
      endTask(agentId);
    }

    var nowMs = _startTime ? (Date.now() - _startTime) : 0;
    var agentCfg = CONFIG.AGENTS[agentId];
    var color = agentCfg ? agentCfg.color : '#888';

    var bar = el('div', 'tl-bar tl-bar--active');
    bar.style.left = msToX(nowMs) + 'px';
    bar.style.width = '0px';
    bar.style.top = BAR_V_PAD + 'px';
    bar.style.height = BAR_HEIGHT + 'px';
    bar.style.backgroundColor = color;

    /* Label inside bar */
    var barLabel = el('span', 'tl-bar-label');
    barLabel.textContent = taskLabel || '';
    bar.appendChild(barLabel);

    _laneEls[agentId].appendChild(bar);

    _activeBars[agentId] = {
      el: bar,
      startMs: nowMs,
      label: taskLabel
    };
  }

  function endTask(agentId) {
    var active = _activeBars[agentId];
    if (!active) return;

    var nowMs = _startTime ? (Date.now() - _startTime) : 0;
    var width = msToX(nowMs - active.startMs);
    if (width < 2) width = 2;
    active.el.style.width = width + 'px';
    active.el.classList.remove('tl-bar--active');
    active.el.classList.add('tl-bar--complete');

    _allBars.push({
      el: active.el,
      agentId: agentId,
      startMs: active.startMs,
      endMs: nowMs
    });

    delete _activeBars[agentId];
  }

  function growActiveBars(elapsedMs) {
    var keys = Object.keys(_activeBars);
    for (var i = 0; i < keys.length; i++) {
      var agentId = keys[i];
      var active = _activeBars[agentId];
      if (!active) continue;
      var width = msToX(elapsedMs - active.startMs);
      if (width < 0) width = 0;
      active.el.style.width = width + 'px';
    }
  }

  /* ======================================================================
     Phase Markers
     ====================================================================== */
  function addPhaseMarker(label, timestamp) {
    if (!_canvasInner) return;
    var offsetMs = timestamp || (AppState.demoStartTime ? (Date.now() - AppState.demoStartTime) : 0);
    var x = msToX(offsetMs);

    var marker = el('div', 'tl-phase-marker');
    marker.style.left = x + 'px';
    marker.style.height = (TIME_AXIS_H + LANE_ORDER.length * LANE_HEIGHT) + 'px';

    var markerLabel = el('div', 'tl-phase-label');
    markerLabel.textContent = label;
    marker.appendChild(markerLabel);

    _canvasInner.appendChild(marker);
    _phases.push({ el: marker, label: label, offsetMs: offsetMs });
  }

  /* ======================================================================
     Reset
     ====================================================================== */
  function reset() {
    _activeBars = {};
    _allBars = [];
    _phases = [];
    _startTime = null;
    buildDOM();
  }

  /* ======================================================================
     Event Handlers
     ====================================================================== */

  /* agent:update -> { name, status }
     Map status to start/end task bars */
  function onAgentUpdate(data) {
    if (!data || !data.name) return;
    var agentId = data.name;
    var status  = data.status;
    var agent   = AppState.agents[agentId];
    var desc    = agent ? agent.taskDescription : '';

    switch (status) {
      case 'working':
      case 'thinking':
        startTask(agentId, desc || status);
        break;
      case 'done':
      case 'idle':
      case 'error':
        endTask(agentId);
        break;
    }
  }

  /* demo:tick -> elapsedMs */
  function onTick(elapsedMs) {
    if (!_startTime) _startTime = AppState.demoStartTime;
    setCanvasWidth(elapsedMs);
    updateAxis(elapsedMs);
    updateNowCursor(elapsedMs);
    growActiveBars(elapsedMs);
    autoScroll(elapsedMs);
  }

  /* phase:change -> { label, timestamp? } */
  function onPhaseChange(data) {
    if (!data) return;
    addPhaseMarker(data.label, data.timestamp);
  }

  /* state:reset */
  function onReset() {
    reset();
  }

  /* demo:start — record the start time for timeline positioning */
  function onDemoStart() {
    _startTime = AppState.demoStartTime;
  }

  /* ======================================================================
     Init
     ====================================================================== */
  buildDOM();

  EventBus.on('agent:update', onAgentUpdate);
  EventBus.on('demo:tick', onTick);
  EventBus.on('phase:change', onPhaseChange);
  EventBus.on('state:reset', onReset);
  EventBus.on('demo:start', onDemoStart);

  /* Expose public API */
  window.timelineComponent = {
    init: function () { buildDOM(); },
    startTask: startTask,
    endTask: endTask,
    addPhaseMarker: addPhaseMarker,
    reset: reset
  };
});
