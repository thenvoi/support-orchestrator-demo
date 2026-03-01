/* ==========================================================================
   Support Orchestrator — Message Flow Panel Component
   ========================================================================== */

window.registerComponent('messageFlow', function (deps) {
  'use strict';

  var EventBus = deps.EventBus;
  var AppState = deps.AppState;
  var CONFIG   = deps.CONFIG;

  /* ---- DOM references ---- */
  var container   = document.getElementById('message-flow-container');
  var messageList = document.getElementById('message-list');
  var countBadge  = document.getElementById('message-count');

  if (!container || !messageList) {
    console.warn('[MessageFlow] Required container elements not found');
    return;
  }

  /* ---- Internal state ---- */
  var messageCount = 0;
  var autoScroll   = true;

  /* ======================================================================
     Init — render the empty state
     ====================================================================== */
  function init() {
    renderEmptyState();
    wireScrollDetection();
  }

  function renderEmptyState() {
    messageList.innerHTML = '';
    messageList.innerHTML =
      '<div class="message-list__empty">' +
        '<div class="message-list__empty-icon">&#x1F4E8;</div>' +
        '<div class="message-list__empty-text">No messages yet.<br>Run a demo to see agent communication.</div>' +
      '</div>';
  }

  /* ======================================================================
     addMessage — create a message entry with slide-in animation
     ====================================================================== */
  function addMessage(from, to, type, content, timestamp) {
    /* Remove empty state on first message */
    var emptyEl = messageList.querySelector('.message-list__empty');
    if (emptyEl) {
      emptyEl.remove();
    }

    messageCount++;
    updateBadge();

    /* Resolve agent display info */
    var fromAgent = CONFIG.AGENTS[from] || { displayName: from, color: '#94a3b8' };
    var toAgent   = CONFIG.AGENTS[to]   || { displayName: to || 'All', color: '#94a3b8' };

    /* Compute relative timestamp */
    var relativeTime = '0.0s';
    if (AppState.demoStartTime && timestamp) {
      var offsetSec = (timestamp - AppState.demoStartTime) / 1000;
      relativeTime = offsetSec.toFixed(1) + 's';
    }

    /* Truncate preview — prefer the text field for readability */
    var contentText = typeof content === 'string'
      ? content
      : (content && content.text ? content.text : JSON.stringify(content));
    var preview = contentText.length > 120
      ? contentText.substring(0, 120) + '...'
      : contentText;

    /* Build entry element */
    var entry = document.createElement('div');
    entry.className = 'mf-entry';
    entry.setAttribute('data-msg-id', 'mf-' + messageCount);

    /* Build badge class from type */
    var badgeClass = 'mf-entry__badge mf-entry__badge--' + type;
    var badgeLabel = formatBadgeLabel(type);

    /* Route display — handle cases where to is absent */
    var routeLabel = '';
    if (to && to !== from) {
      routeLabel = fromAgent.displayName +
        ' <span class="mf-entry__arrow">&rarr;</span> ' +
        toAgent.displayName;
    } else {
      routeLabel = fromAgent.displayName;
    }

    entry.innerHTML =
      '<div class="mf-entry__header">' +
        '<span class="mf-entry__dot" style="background:' + fromAgent.color + ';box-shadow:0 0 4px ' + fromAgent.color + '50;"></span>' +
        '<span class="mf-entry__route">' + routeLabel + '</span>' +
        '<span class="' + badgeClass + '">' + badgeLabel + '</span>' +
        '<span class="mf-entry__time">' + relativeTime + '</span>' +
        '<span class="mf-entry__expand-hint">&#x25B8;</span>' +
      '</div>' +
      '<div class="mf-entry__preview">' + escapeHtml(preview) + '</div>' +
      '<div class="mf-entry__detail">' +
        '<div class="mf-json">' + syntaxHighlight(content, fromAgent.color) + '</div>' +
      '</div>';

    /* Click to expand/collapse */
    entry.addEventListener('click', function () {
      entry.classList.toggle('mf-entry--expanded');
    });

    /* Append and animate */
    messageList.appendChild(entry);

    /* Brief highlight flash */
    requestAnimationFrame(function () {
      entry.classList.add('mf-entry--flash');
    });

    /* Auto-scroll to bottom */
    if (autoScroll) {
      scrollToBottom();
    }
  }

  /* ======================================================================
     clear — remove all messages and reset
     ====================================================================== */
  function clear() {
    messageCount = 0;
    updateBadge();
    renderEmptyState();
    autoScroll = true;
  }

  /* ======================================================================
     Helpers
     ====================================================================== */

  function updateBadge() {
    if (countBadge) {
      countBadge.textContent = messageCount + ' message' + (messageCount !== 1 ? 's' : '');
    }
  }

  function scrollToBottom() {
    requestAnimationFrame(function () {
      messageList.scrollTop = messageList.scrollHeight;
    });
  }

  /** Detect manual scroll to disable auto-scroll; re-enable if scrolled to bottom */
  function wireScrollDetection() {
    messageList.addEventListener('scroll', function () {
      var threshold = 40;
      var atBottom = (messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight) < threshold;
      autoScroll = atBottom;
    });
  }

  function formatBadgeLabel(type) {
    switch (type) {
      case 'task_request':    return 'Request';
      case 'task_result':     return 'Result';
      case 'user_message':    return 'User';
      case 'acknowledgment':  return 'Ack';
      case 'dispatch':        return 'Dispatch';
      case 'final_response':  return 'Response';
      case 'status':          return 'Status';
      case 'result':          return 'Result';
      default:                return type;
    }
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  /* ======================================================================
     JSON Syntax Highlighting
     ====================================================================== */

  /**
   * Convert a value to syntax-highlighted HTML.
   * Keys use the agent's accent color; strings green; numbers blue.
   */
  function syntaxHighlight(value, agentColor) {
    var json;
    if (typeof value === 'string') {
      /* Try to parse as JSON first */
      try {
        var parsed = JSON.parse(value);
        json = JSON.stringify(parsed, null, 2);
      } catch (e) {
        /* Plain string — wrap in a simple object for display */
        json = JSON.stringify({ message: value }, null, 2);
      }
    } else if (typeof value === 'object' && value !== null) {
      json = JSON.stringify(value, null, 2);
    } else {
      json = JSON.stringify({ value: value }, null, 2);
    }

    /* Escape HTML entities in the JSON string first */
    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    /* Tokenize and colorize */
    var keyColor = agentColor || '#a78bfa';

    var highlighted = json.replace(
      /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*")\s*:/g,
      function (match, key) {
        return '<span class="mf-json-key" style="color:' + keyColor + '">' + key + '</span>:';
      }
    );

    highlighted = highlighted.replace(
      /:\s*("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*")/g,
      function (match, str) {
        return ': <span class="mf-json-string">' + str + '</span>';
      }
    );

    /* Standalone strings (array values, etc.) */
    highlighted = highlighted.replace(
      /(?<=[\[,\n]\s*)("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*")(?=\s*[,\]\n])/g,
      function (match) {
        return '<span class="mf-json-string">' + match + '</span>';
      }
    );

    highlighted = highlighted.replace(
      /\b(-?\d+\.?\d*(?:e[+-]?\d+)?)\b/g,
      '<span class="mf-json-number">$1</span>'
    );

    highlighted = highlighted.replace(
      /\b(true|false)\b/g,
      '<span class="mf-json-bool">$1</span>'
    );

    highlighted = highlighted.replace(
      /\bnull\b/g,
      '<span class="mf-json-null">null</span>'
    );

    return '<pre class="mf-entry__json">' + highlighted + '</pre>';
  }

  /* ======================================================================
     EventBus Listeners
     ====================================================================== */

  /**
   * Listen for 'message:new' events emitted by the DemoRunner / WS handler.
   * Map internal message types to the panel's display format.
   */
  EventBus.on('message:new', function (msg) {
    var from = msg.from || 'unknown';
    var to   = msg.to   || '';
    var type = msg.type  || 'status';
    var timestamp = msg.timestamp || Date.now();

    /* Build a content object with all available payload fields */
    var content;
    switch (type) {
      case 'user_message':
        content = { type: 'user_message', text: msg.text };
        break;

      case 'dispatch':
        content = {
          type: 'dispatch',
          text: msg.text,
          targets: msg.targets,
          tasks: msg.tasks
        };
        /* For dispatch, we show the orchestrator sending to multiple targets */
        to = (msg.targets && msg.targets.length > 0)
          ? msg.targets[0]
          : 'agents';
        break;

      case 'status':
        content = {
          type: 'status',
          status: msg.status,
          text: msg.text
        };
        to = '';
        break;

      case 'result':
        content = {
          type: 'result',
          text: msg.text
        };
        break;

      case 'final_response':
        content = {
          type: 'final_response',
          text: msg.text
        };
        break;

      default:
        content = { type: type, text: msg.text || '' };
    }

    /* Derive a display text for the preview line */
    var previewText = msg.text || JSON.stringify(content);

    addMessage(from, to, type, content, timestamp);
  });

  /** Reset on state:reset */
  EventBus.on('state:reset', function () {
    clear();
  });

  /* ======================================================================
     Kick off
     ====================================================================== */
  init();

  console.log('[MessageFlow] Component initialized');
});
