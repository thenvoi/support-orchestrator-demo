/* ==========================================================================
   Support Orchestrator — Topology Visualization (SVG)
   ========================================================================== */

(function () {
  'use strict';

  /* ======================================================================
     Constants
     ====================================================================== */
  var SVG_NS = 'http://www.w3.org/2000/svg';

  var NODE_DEFS = {
    user:         { x: 450, y: 70,  r: 28, type: 'user' },
    orchestrator: { x: 450, y: 230, r: 45, type: 'hub' },
    excel:        { x: 150, y: 400, r: 32, type: 'spoke' },
    github:       { x: 350, y: 430, r: 32, type: 'spoke' },
    browser:      { x: 550, y: 430, r: 32, type: 'spoke' },
    linear:       { x: 750, y: 400, r: 32, type: 'spoke' }
  };

  /* Connection definitions: from -> to with curve offset */
  var CONNECTIONS = [
    { from: 'user',         to: 'orchestrator', curve: 0 },
    { from: 'orchestrator', to: 'excel',        curve: -40 },
    { from: 'orchestrator', to: 'github',       curve: -20 },
    { from: 'orchestrator', to: 'browser',      curve: 20 },
    { from: 'orchestrator', to: 'linear',       curve: 40 }
  ];

  var PARTICLE_SPEED = 2.5;         /* pixels per frame at 60fps */
  var PARTICLE_TRAIL_COUNT = 3;
  var PARTICLE_TRAIL_SPACING = 12;  /* px between trail copies */
  var PARTICLE_RADIUS = 4;

  /* ======================================================================
     Module state
     ====================================================================== */
  var EventBus, AppState, CONFIG;
  var svg, defsEl, connectionsGroup, particlesGroup, nodesGroup;
  var nodeElements = {};     /* agentId -> { group, circle, glowCircle, icon, label, statusRing, spinRing } */
  var connectionPaths = {};  /* "from->to" -> { path, fromId, toId } */
  var activeParticles = [];  /* array of particle objects in flight */
  var animFrameId = null;

  /* ======================================================================
     SVG Element Helpers
     ====================================================================== */
  function svgEl(tag, attrs) {
    var el = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      var keys = Object.keys(attrs);
      for (var i = 0; i < keys.length; i++) {
        el.setAttribute(keys[i], attrs[keys[i]]);
      }
    }
    return el;
  }

  function hexToRgb(hex) {
    hex = hex.replace('#', '');
    return {
      r: parseInt(hex.substring(0, 2), 16),
      g: parseInt(hex.substring(2, 4), 16),
      b: parseInt(hex.substring(4, 6), 16)
    };
  }

  /* ======================================================================
     Build SVG Defs (gradients, filters)
     ====================================================================== */
  function buildDefs() {
    defsEl = svgEl('defs');

    /* --- Per-agent radial gradients --- */
    var agentKeys = Object.keys(CONFIG.AGENTS);
    for (var i = 0; i < agentKeys.length; i++) {
      var agentId = agentKeys[i];
      var color = CONFIG.AGENTS[agentId].color;
      var rgb = hexToRgb(color);

      /* Fill gradient */
      var grad = svgEl('radialGradient', {
        id: 'grad-' + agentId,
        cx: '40%', cy: '35%', r: '65%'
      });
      var stop1 = svgEl('stop', {
        offset: '0%',
        'stop-color': 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.95)'
      });
      var stop2 = svgEl('stop', {
        offset: '100%',
        'stop-color': 'rgba(' + Math.max(0, rgb.r - 40) + ',' + Math.max(0, rgb.g - 40) + ',' + Math.max(0, rgb.b - 40) + ',0.85)'
      });
      grad.appendChild(stop1);
      grad.appendChild(stop2);
      defsEl.appendChild(grad);

      /* Glow filter */
      var filter = svgEl('filter', {
        id: 'glow-' + agentId,
        x: '-50%', y: '-50%',
        width: '200%', height: '200%'
      });
      var feBlur = svgEl('feGaussianBlur', {
        'in': 'SourceGraphic',
        stdDeviation: '6',
        result: 'blur'
      });
      var feColorMatrix = svgEl('feColorMatrix', {
        'in': 'blur',
        type: 'matrix',
        values: '1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.6 0'
      });
      var feMerge = svgEl('feMerge');
      var mergeNode1 = svgEl('feMergeNode');
      var mergeNode2 = svgEl('feMergeNode', { 'in': 'SourceGraphic' });
      feMerge.appendChild(mergeNode1);
      feMerge.appendChild(mergeNode2);
      filter.appendChild(feBlur);
      filter.appendChild(feColorMatrix);
      filter.appendChild(feMerge);
      defsEl.appendChild(filter);
    }

    /* --- Connection glow filter --- */
    var connGlow = svgEl('filter', {
      id: 'connection-glow',
      x: '-20%', y: '-20%',
      width: '140%', height: '140%'
    });
    var connBlur = svgEl('feGaussianBlur', {
      'in': 'SourceGraphic',
      stdDeviation: '3',
      result: 'blur'
    });
    var connMerge = svgEl('feMerge');
    var cMerge1 = svgEl('feMergeNode');
    var cMerge2 = svgEl('feMergeNode', { 'in': 'SourceGraphic' });
    connMerge.appendChild(cMerge1);
    connMerge.appendChild(cMerge2);
    connGlow.appendChild(connBlur);
    connGlow.appendChild(connMerge);
    defsEl.appendChild(connGlow);

    /* --- Particle glow filter --- */
    var particleGlow = svgEl('filter', {
      id: 'particle-glow',
      x: '-100%', y: '-100%',
      width: '300%', height: '300%'
    });
    var pBlur = svgEl('feGaussianBlur', {
      'in': 'SourceGraphic',
      stdDeviation: '3',
      result: 'blur'
    });
    var pMerge = svgEl('feMerge');
    var pMerge1 = svgEl('feMergeNode');
    var pMerge2 = svgEl('feMergeNode', { 'in': 'SourceGraphic' });
    pMerge.appendChild(pMerge1);
    pMerge.appendChild(pMerge2);
    particleGlow.appendChild(pBlur);
    particleGlow.appendChild(pMerge);
    defsEl.appendChild(particleGlow);

    svg.appendChild(defsEl);
  }

  /* ======================================================================
     Build Connection Paths
     ====================================================================== */
  function buildPathD(fromId, toId, curveOffset) {
    var from = NODE_DEFS[fromId];
    var to   = NODE_DEFS[toId];

    if (curveOffset === 0) {
      /* Straight line */
      return 'M ' + from.x + ' ' + from.y + ' L ' + to.x + ' ' + to.y;
    }

    /* Quadratic bezier curve */
    var mx = (from.x + to.x) / 2 + curveOffset;
    var my = (from.y + to.y) / 2;
    return 'M ' + from.x + ' ' + from.y + ' Q ' + mx + ' ' + my + ' ' + to.x + ' ' + to.y;
  }

  function buildConnections() {
    connectionsGroup = svgEl('g', { class: 'topology-connections' });

    for (var i = 0; i < CONNECTIONS.length; i++) {
      var conn = CONNECTIONS[i];
      var key = conn.from + '->' + conn.to;
      var agentColor = CONFIG.AGENTS[conn.to].color;
      var d = buildPathD(conn.from, conn.to, conn.curve);
      var isDashed = (conn.to === 'linear' || conn.from === 'linear');

      var pathAttrs = {
        d: d,
        fill: 'none',
        stroke: agentColor,
        'stroke-width': '2',
        'stroke-opacity': '0.3',
        'stroke-linecap': 'round',
        class: 'topology-connection',
        'data-from': conn.from,
        'data-to': conn.to
      };

      if (isDashed) {
        pathAttrs['stroke-dasharray'] = '8 4';
      }

      var path = svgEl('path', pathAttrs);
      connectionsGroup.appendChild(path);

      connectionPaths[key] = {
        path: path,
        fromId: conn.from,
        toId: conn.to
      };

      /* Also store the reverse key for result particles */
      connectionPaths[conn.to + '->' + conn.from] = {
        path: path,
        fromId: conn.from,
        toId: conn.to,
        reversed: true
      };
    }

    svg.appendChild(connectionsGroup);
  }

  /* ======================================================================
     Build Nodes
     ====================================================================== */
  function buildNodes() {
    nodesGroup = svgEl('g', { class: 'topology-nodes' });

    var agentOrder = ['excel', 'github', 'browser', 'linear', 'orchestrator', 'user'];

    for (var i = 0; i < agentOrder.length; i++) {
      var agentId = agentOrder[i];
      var def = NODE_DEFS[agentId];
      var agentCfg = CONFIG.AGENTS[agentId];
      var color = agentCfg.color;
      var rgb = hexToRgb(color);

      var group = svgEl('g', {
        class: 'topology-node',
        'data-agent': agentId,
        transform: 'translate(' + def.x + ',' + def.y + ')'
      });

      /* Outer glow circle (animated) */
      var glowAnimName;
      if (def.type === 'hub') {
        glowAnimName = 'pulse-glow';
      } else if (def.type === 'user') {
        glowAnimName = 'pulse-glow-user';
      } else {
        glowAnimName = 'pulse-glow-small';
      }

      var glowCircle = svgEl('circle', {
        cx: '0', cy: '0',
        r: String(def.r + 8),
        fill: 'none',
        stroke: 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.25)',
        'stroke-width': '2',
        opacity: '0'
      });
      glowCircle.style.animation = glowAnimName + ' 2.5s ease-in-out infinite';
      group.appendChild(glowCircle);

      /* Spinning status ring (visible when working) */
      var spinRing = svgEl('circle', {
        cx: '0', cy: '0',
        r: String(def.r + 4),
        fill: 'none',
        stroke: color,
        'stroke-width': '2',
        'stroke-dasharray': String(Math.PI * (def.r + 4) * 0.3) + ' ' + String(Math.PI * (def.r + 4) * 0.7),
        'stroke-linecap': 'round',
        opacity: '0',
        class: 'node-spin-ring'
      });
      group.appendChild(spinRing);

      /* Status ring (stroke changes color based on state) */
      var statusRing = svgEl('circle', {
        cx: '0', cy: '0',
        r: String(def.r + 1),
        fill: 'none',
        stroke: 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.15)',
        'stroke-width': '2',
        class: 'node-status-ring'
      });
      group.appendChild(statusRing);

      /* Main circle with gradient fill */
      var circle = svgEl('circle', {
        cx: '0', cy: '0',
        r: String(def.r),
        fill: 'url(#grad-' + agentId + ')',
        filter: 'url(#glow-' + agentId + ')',
        class: 'node-circle'
      });
      group.appendChild(circle);

      /* Icon emoji */
      var icon = svgEl('text', {
        x: '0', y: '0',
        'text-anchor': 'middle',
        'dominant-baseline': 'central',
        'font-size': def.type === 'hub' ? '28' : (def.type === 'user' ? '20' : '22'),
        class: 'node-icon',
        style: 'pointer-events:none;'
      });
      icon.textContent = agentCfg.icon;
      group.appendChild(icon);

      /* Label below node */
      var label = svgEl('text', {
        x: '0',
        y: String(def.r + 18),
        'text-anchor': 'middle',
        'font-size': '12',
        'font-weight': '600',
        fill: '#94a3b8',
        class: 'node-label',
        style: 'pointer-events:none;'
      });
      label.textContent = agentCfg.displayName;
      group.appendChild(label);

      nodesGroup.appendChild(group);

      nodeElements[agentId] = {
        group: group,
        circle: circle,
        glowCircle: glowCircle,
        icon: icon,
        label: label,
        statusRing: statusRing,
        spinRing: spinRing
      };
    }

    svg.appendChild(nodesGroup);
  }

  /* ======================================================================
     Node Status Updates
     ====================================================================== */
  function setNodeStatus(agentId, status) {
    var node = nodeElements[agentId];
    if (!node) return;

    var agentCfg = CONFIG.AGENTS[agentId];
    if (!agentCfg) return;
    var color = agentCfg.color;
    var rgb = hexToRgb(color);

    switch (status) {
      case 'idle':
        node.glowCircle.setAttribute('opacity', '0');
        node.spinRing.setAttribute('opacity', '0');
        node.spinRing.classList.remove('node-spin-ring--active');
        node.statusRing.setAttribute('stroke', 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.15)');
        node.circle.setAttribute('opacity', '0.7');
        break;

      case 'working':
      case 'thinking':
        node.glowCircle.setAttribute('opacity', '1');
        node.spinRing.setAttribute('opacity', '1');
        node.spinRing.classList.add('node-spin-ring--active');
        node.statusRing.setAttribute('stroke', 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.6)');
        node.circle.setAttribute('opacity', '1');
        break;

      case 'done':
        node.glowCircle.setAttribute('opacity', '0.6');
        node.spinRing.setAttribute('opacity', '0');
        node.spinRing.classList.remove('node-spin-ring--active');
        node.statusRing.setAttribute('stroke', 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.8)');
        node.statusRing.setAttribute('stroke-width', '3');
        node.circle.setAttribute('opacity', '1');
        break;

      case 'error':
        node.glowCircle.setAttribute('stroke', 'rgba(239,68,68,0.4)');
        node.glowCircle.setAttribute('opacity', '0.8');
        node.spinRing.setAttribute('opacity', '0');
        node.spinRing.classList.remove('node-spin-ring--active');
        node.statusRing.setAttribute('stroke', 'rgba(239,68,68,0.6)');
        node.circle.setAttribute('opacity', '1');
        break;

      default:
        break;
    }
  }

  /* ======================================================================
     Connection Line Activation
     ====================================================================== */
  function activateConnection(fromId, toId) {
    var key = fromId + '->' + toId;
    var conn = connectionPaths[key];
    if (!conn) return;

    var path = conn.path;
    var color = CONFIG.AGENTS[toId] ? CONFIG.AGENTS[toId].color : CONFIG.AGENTS[fromId].color;
    path.setAttribute('stroke-opacity', '0.8');
    path.setAttribute('stroke-width', '3');
    path.classList.add('topology-connection--active');

    /* Fade back after animation */
    setTimeout(function () {
      path.setAttribute('stroke-opacity', '0.3');
      path.setAttribute('stroke-width', '2');
      path.classList.remove('topology-connection--active');
    }, 1500);
  }

  /* ======================================================================
     Path Length & Point-at-Length Helpers
     ====================================================================== */
  function getPathLength(pathEl) {
    return pathEl.getTotalLength();
  }

  function getPointAtLength(pathEl, len) {
    return pathEl.getPointAtLength(len);
  }

  /* ======================================================================
     Particle System
     ====================================================================== */
  function createParticleElements(color) {
    var rgb = hexToRgb(color);
    var elements = [];

    /* Main particle + trail copies */
    for (var i = 0; i <= PARTICLE_TRAIL_COUNT; i++) {
      var opacity = i === 0 ? 1.0 : Math.max(0.1, 1.0 - (i * 0.3));
      var radius  = i === 0 ? PARTICLE_RADIUS : Math.max(1.5, PARTICLE_RADIUS - (i * 0.8));

      var circle = svgEl('circle', {
        cx: '0', cy: '0',
        r: String(radius),
        fill: 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',' + opacity + ')',
        filter: i === 0 ? 'url(#particle-glow)' : '',
        opacity: '0',
        class: i === 0 ? 'topology-particle' : 'topology-particle-trail'
      });
      particlesGroup.appendChild(circle);
      elements.push(circle);
    }

    return elements;
  }

  function sendParticle(fromAgent, toAgent) {
    /* Find the connection path */
    var key = fromAgent + '->' + toAgent;
    var conn = connectionPaths[key];
    if (!conn) return;

    var pathEl = conn.path;
    var totalLength = getPathLength(pathEl);
    var reversed = !!conn.reversed;

    /* Choose color from the moving-from agent */
    var color = CONFIG.AGENTS[fromAgent] ? CONFIG.AGENTS[fromAgent].color : '#8b5cf6';
    var elements = createParticleElements(color);

    /* Activate the connection line */
    activateConnection(fromAgent, toAgent);

    activeParticles.push({
      elements: elements,
      pathEl: pathEl,
      totalLength: totalLength,
      progress: 0,
      reversed: reversed,
      speed: PARTICLE_SPEED
    });

    /* Ensure animation loop is running */
    if (!animFrameId) {
      animFrameId = requestAnimationFrame(animateParticles);
    }
  }

  function animateParticles(timestamp) {
    var i = activeParticles.length;

    while (i--) {
      var p = activeParticles[i];
      p.progress += p.speed;

      if (p.progress >= p.totalLength) {
        /* Remove particle elements */
        for (var j = 0; j < p.elements.length; j++) {
          if (p.elements[j].parentNode) {
            p.elements[j].parentNode.removeChild(p.elements[j]);
          }
        }
        activeParticles.splice(i, 1);
        continue;
      }

      /* Position each element along the path */
      for (var k = 0; k < p.elements.length; k++) {
        var offset = k * PARTICLE_TRAIL_SPACING;
        var len;

        if (p.reversed) {
          len = p.totalLength - (p.progress - offset);
        } else {
          len = p.progress - offset;
        }

        if (len < 0 || len > p.totalLength) {
          p.elements[k].setAttribute('opacity', '0');
          continue;
        }

        var pt = getPointAtLength(p.pathEl, len);
        p.elements[k].setAttribute('cx', pt.x);
        p.elements[k].setAttribute('cy', pt.y);
        p.elements[k].setAttribute('opacity', k === 0 ? '1' : String(Math.max(0.1, 1.0 - (k * 0.3))));
      }
    }

    if (activeParticles.length > 0) {
      animFrameId = requestAnimationFrame(animateParticles);
    } else {
      animFrameId = null;
    }
  }

  /* ======================================================================
     Reset
     ====================================================================== */
  function reset() {
    /* Reset all nodes to idle */
    var agentKeys = Object.keys(nodeElements);
    for (var i = 0; i < agentKeys.length; i++) {
      setNodeStatus(agentKeys[i], 'idle');
      /* Also reset stroke-width on done state */
      var node = nodeElements[agentKeys[i]];
      if (node) {
        node.statusRing.setAttribute('stroke-width', '2');
      }
    }

    /* Remove all active particles */
    for (var j = activeParticles.length - 1; j >= 0; j--) {
      var p = activeParticles[j];
      for (var k = 0; k < p.elements.length; k++) {
        if (p.elements[k].parentNode) {
          p.elements[k].parentNode.removeChild(p.elements[k]);
        }
      }
    }
    activeParticles = [];

    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }

    /* Reset connection paths */
    var pathKeys = Object.keys(connectionPaths);
    for (var m = 0; m < pathKeys.length; m++) {
      var path = connectionPaths[pathKeys[m]].path;
      path.setAttribute('stroke-opacity', '0.3');
      path.setAttribute('stroke-width', '2');
      path.classList.remove('topology-connection--active');
    }
  }

  /* ======================================================================
     Initialization
     ====================================================================== */
  function init(deps) {
    EventBus = deps.EventBus;
    AppState = deps.AppState;
    CONFIG   = deps.CONFIG;

    var container = document.getElementById('topology-canvas');
    if (!container) {
      console.error('[Topology] #topology-canvas not found');
      return;
    }

    /* Create SVG root */
    svg = svgEl('svg', {
      viewBox: '0 0 900 500',
      preserveAspectRatio: 'xMidYMid meet',
      class: 'topology-svg'
    });

    /* Background subtle grid pattern */
    buildDefs();

    /* Add a subtle background rect */
    var bgRect = svgEl('rect', {
      x: '0', y: '0',
      width: '900', height: '500',
      fill: 'transparent'
    });
    svg.appendChild(bgRect);

    /* Build layers in order: connections -> particles -> nodes */
    buildConnections();

    particlesGroup = svgEl('g', { class: 'topology-particles' });
    svg.appendChild(particlesGroup);

    buildNodes();

    container.appendChild(svg);

    /* --- Event Listeners --- */

    /* agent:update -> update node visual status */
    EventBus.on('agent:update', function (data) {
      if (data && data.name && data.status) {
        setNodeStatus(data.name, data.status);
      }
    });

    /* topology:dispatch -> particle from orchestrator to target */
    EventBus.on('topology:dispatch', function (data) {
      if (data && data.from && data.to) {
        sendParticle(data.from, data.to);
      }
    });

    /* topology:result -> particle from agent back to orchestrator */
    EventBus.on('topology:result', function (data) {
      if (data && data.from && data.to) {
        sendParticle(data.from, data.to);
      }
    });

    /* message:new -> particle for user messages and final responses */
    EventBus.on('message:new', function (msg) {
      if (!msg) return;
      if (msg.type === 'user_message' && msg.from && msg.to) {
        sendParticle(msg.from, msg.to);
      }
      if (msg.type === 'final_response' && msg.from && msg.to) {
        sendParticle(msg.from, msg.to);
      }
    });

    /* state:reset -> reset all visuals */
    EventBus.on('state:reset', function () {
      reset();
    });

    /* Set initial idle state */
    var agentKeys = Object.keys(NODE_DEFS);
    for (var i = 0; i < agentKeys.length; i++) {
      setNodeStatus(agentKeys[i], 'idle');
    }

    console.log('[Topology] SVG visualization initialized');
  }

  /* ======================================================================
     Register Component
     ====================================================================== */
  window.registerComponent('topology', function (deps) {
    init(deps);
  });

})();
