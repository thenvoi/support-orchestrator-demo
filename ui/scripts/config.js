/* ==========================================================================
   Support Orchestrator — Configuration
   ========================================================================== */

window.CONFIG = Object.freeze({

  /* ---- Agent Definitions ---- */
  AGENTS: {
    user: {
      name: 'user',
      displayName: 'Customer',
      color: '#06b6d4',
      darkColor: 'rgba(6, 182, 212, 0.12)',
      icon: '\uD83D\uDC64',
      roomLabel: 'Customer',
      domain: 'End-user submitting a support request'
    },
    orchestrator: {
      name: 'orchestrator',
      displayName: 'Orchestrator',
      color: '#8b5cf6',
      darkColor: 'rgba(139, 92, 246, 0.12)',
      icon: '\uD83E\uDDE0',
      roomLabel: 'Orchestrator',
      domain: 'Central coordinator that routes tasks to specialist agents'
    },
    excel: {
      name: 'excel',
      displayName: 'Excel Agent',
      color: '#10b981',
      darkColor: 'rgba(16, 185, 129, 0.12)',
      icon: '\uD83D\uDCCA',
      roomLabel: 'CRM Room',
      domain: 'Queries CRM spreadsheets for customer data, plans, and history'
    },
    github: {
      name: 'github',
      displayName: 'GitHub Agent',
      color: '#f59e0b',
      darkColor: 'rgba(245, 158, 11, 0.12)',
      icon: '\uD83D\uDC19',
      roomLabel: 'GitHub Room',
      domain: 'Searches repositories for issues, PRs, and code references'
    },
    browser: {
      name: 'browser',
      displayName: 'Browser Agent',
      color: '#3b82f6',
      darkColor: 'rgba(59, 130, 246, 0.12)',
      icon: '\uD83C\uDF10',
      roomLabel: 'Browser Room',
      domain: 'Navigates documentation sites and knowledge bases'
    },
    linear: {
      name: 'linear',
      displayName: 'Linear Agent',
      color: '#ec4899',
      darkColor: 'rgba(236, 72, 153, 0.12)',
      icon: '\uD83D\uDCCB',
      roomLabel: 'Linear Room',
      domain: 'Manages project-tracking tickets and workflow states'
    }
  },

  /* ---- Agent Name Mapping (Thenvoi agent names → UI agent keys) ---- */
  AGENT_NAME_MAP: {
    'SupportOrchestrator': 'orchestrator',
    'ExcelAgent': 'excel',
    'GitHubSupportAgent': 'github',
    'BrowserAgent': 'browser',
    'LinearAgent': 'linear'
  },

  /* ---- WebSocket ---- */
  WS_URL: 'ws://localhost:8765',

  /* ---- Timing Constants ---- */
  TIMING: {
    RECONNECT_DELAY: 3000,
    RECONNECT_MAX_DELAY: 30000,
    HEARTBEAT_INTERVAL: 15000,
    MESSAGE_ANIMATION_MS: 300,
    TOPOLOGY_PULSE_MS: 600,
    TIMELINE_TICK_MS: 100,
    LOADING_SCREEN_MS: 1800,
    DEMO_SPEED_MULTIPLIER: 1
  },

  /* ---- Demo Scenarios ---- */
  DEMO_SCENARIOS: {
    branchA: {
      id: 'branchA',
      name: 'Known Bug Flow',
      description: 'sarah@acme.com reports a known bug — orchestrator fans out to Excel, GitHub, and Browser agents in parallel.',
      customerEmail: 'sarah@acme.com',

      events: [
        /* t=0ms — Customer sends initial message */
        {
          t: 0,
          type: 'user_message',
          from: 'user',
          to: 'orchestrator',
          payload: {
            text: 'Hi, I\'m sarah@acme.com. The dashboard export to PDF has been broken since last Tuesday. It just spins forever and never downloads. This is blocking our weekly reporting. Can you help?'
          }
        },

        /* t=500ms — Orchestrator acknowledges receipt */
        {
          t: 500,
          type: 'agent_status',
          agent: 'orchestrator',
          status: 'thinking',
          payload: {
            text: 'Received support request from sarah@acme.com. Analyzing the issue and determining which specialist agents to engage...'
          }
        },

        /* t=1000ms — Orchestrator dispatches 3 parallel tasks */
        {
          t: 1000,
          type: 'dispatch',
          from: 'orchestrator',
          targets: ['excel', 'github', 'browser'],
          payload: {
            text: 'Dispatching parallel investigation to 3 specialist agents.',
            tasks: {
              excel: 'Look up customer sarah@acme.com — retrieve account tier, contract status, and any prior support tickets.',
              github: 'Search for issues related to "dashboard PDF export" or "PDF download spinning". Check for recent PRs or fixes.',
              browser: 'Search the product knowledge base and release notes for any known issues or workarounds related to PDF export.'
            }
          }
        },

        /* t=1200ms — Excel agent starts working */
        {
          t: 1200,
          type: 'agent_status',
          agent: 'excel',
          status: 'working',
          payload: {
            text: 'Querying CRM for customer record: sarah@acme.com...'
          }
        },

        /* t=1300ms — GitHub agent starts working */
        {
          t: 1300,
          type: 'agent_status',
          agent: 'github',
          status: 'working',
          payload: {
            text: 'Searching repositories for "dashboard PDF export" issues...'
          }
        },

        /* t=1400ms — Browser agent starts working */
        {
          t: 1400,
          type: 'agent_status',
          agent: 'browser',
          status: 'working',
          payload: {
            text: 'Navigating to knowledge base, searching for PDF export articles...'
          }
        },

        /* t=3000ms — Excel agent completes */
        {
          t: 3000,
          type: 'agent_result',
          agent: 'excel',
          status: 'done',
          payload: {
            text: 'Customer found: Sarah Chen, Acme Corp. Enterprise plan, contract active through 2026-12. Previous ticket #4521 (resolved) about slow exports in Jan 2025. Account in good standing, high-priority support tier.'
          }
        },

        /* t=5000ms — GitHub agent completes */
        {
          t: 5000,
          type: 'agent_result',
          agent: 'github',
          status: 'done',
          payload: {
            text: 'Found issue #1847: "PDF export hangs indefinitely on large dashboards" opened 6 days ago. Labeled as bug, priority P1. Root cause identified — timeout regression in pdf-renderer v3.2.1. Fix merged in PR #1853 but not yet deployed. Hotfix branch: fix/pdf-export-timeout.'
          }
        },

        /* t=8000ms — Browser agent completes */
        {
          t: 8000,
          type: 'agent_result',
          agent: 'browser',
          status: 'done',
          payload: {
            text: 'Knowledge base article KB-2094 confirms known issue with PDF exports since v3.2.1 (released last Tuesday). Workaround available: append "?legacy_render=true" to the dashboard URL before exporting. Fix ETA: next patch release scheduled for Wednesday.'
          }
        },

        /* t=8500ms — Orchestrator synthesizes results */
        {
          t: 8500,
          type: 'agent_status',
          agent: 'orchestrator',
          status: 'thinking',
          phase: 'synthesize',
          payload: {
            text: 'All 3 agents reported back. Synthesizing findings into a unified response for the customer...'
          }
        },

        /* t=10000ms — Orchestrator sends final response */
        {
          t: 10000,
          type: 'final_response',
          from: 'orchestrator',
          to: 'user',
          payload: {
            text: 'Hi Sarah! I\'ve investigated your PDF export issue across our systems. Here\'s what I found:\n\n**Root Cause:** A timeout regression was introduced in our v3.2.1 release last Tuesday (tracked as issue #1847, P1 priority). This affects PDF exports on larger dashboards.\n\n**Immediate Workaround:** Add `?legacy_render=true` to your dashboard URL before exporting. This bypasses the new renderer and should let you complete your weekly reports right away.\n\n**Permanent Fix:** The fix has already been merged (PR #1853) and is scheduled for deployment in Wednesday\'s patch release.\n\nAs an Enterprise customer, I\'ve flagged your account for priority notification when the patch goes live. Is there anything else I can help with?'
          }
        }
      ]
    }
  }
});

/* ==========================================================================
   Component Registry Stub
   Must be defined before component scripts load so they can call
   window.registerComponent(). app.js will later replace this with the
   real implementation that has access to EventBus/AppState, then call
   initAllComponents() to initialize all registered components.
   ========================================================================== */
(function () {
  var _earlyComponents = {};
  window._earlyComponents = _earlyComponents;
  window.registerComponent = function (name, initFn) {
    _earlyComponents[name] = initFn;
  };
})();
