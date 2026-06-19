(function () {
  const messagesEl = document.getElementById('messages');
  const inputEl = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');

  let currentBubble = null;
  let currentSource = null;

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendUserMessage(text) {
    const div = document.createElement('div');
    div.className = 'message user';
    const p = document.createElement('p');
    p.textContent = text;
    div.appendChild(p);
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function createAgentBubble() {
    const div = document.createElement('div');
    div.className = 'message agent';
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  function renderOrderCard(payload) {
    const card = document.createElement('div');
    card.className = 'order-card';

    const header = document.createElement('div');
    header.className = 'order-card-header';

    const idSpan = document.createElement('span');
    idSpan.className = 'order-id';
    idSpan.textContent = 'Order #' + (payload.id || '').slice(0, 8);

    const statusSpan = document.createElement('span');
    const statusLower = (payload.status || '').toLowerCase();
    statusSpan.className = 'status-badge status-' + statusLower;
    statusSpan.textContent = payload.status || '';

    header.appendChild(idSpan);
    header.appendChild(statusSpan);

    const body = document.createElement('div');
    body.className = 'order-card-body';

    const customer = document.createElement('p');
    customer.className = 'customer';
    customer.innerHTML = '<strong>Customer:</strong> ' + escapeHtml(payload.customer_name || '');

    const ul = document.createElement('ul');
    ul.className = 'items-list';
    (payload.items || []).forEach(function (item) {
      const li = document.createElement('li');
      li.textContent = (item.product_name || '') + ' × ' + item.quantity + ' — $' + item.price;
      ul.appendChild(li);
    });

    body.appendChild(customer);
    body.appendChild(ul);
    card.appendChild(header);
    card.appendChild(body);
    return card;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function handleEvent(parsed) {
    if (parsed.type === 'RunStarted') {
      currentBubble = createAgentBubble();
    } else if (parsed.type === 'TextDelta') {
      if (currentBubble) {
        currentBubble.appendChild(document.createTextNode(parsed.delta));
        scrollToBottom();
      }
    } else if (parsed.type === 'ToolCallStart') {
      if (currentBubble) {
        const badge = document.createElement('span');
        badge.className = 'badge tool-start';
        badge.textContent = '🔧 calling ' + parsed.tool_name;
        currentBubble.appendChild(badge);
        scrollToBottom();
      }
    } else if (parsed.type === 'ToolCallResult') {
      if (currentBubble) {
        const badge = document.createElement('span');
        badge.className = 'badge tool-done';
        badge.textContent = '✓ done';
        currentBubble.appendChild(badge);
        scrollToBottom();
      }
    } else if (parsed.type === 'CustomEvent' && parsed.name === 'ui_action') {
      if (currentBubble && parsed.value && parsed.value.action === 'order_card') {
        currentBubble.appendChild(renderOrderCard(parsed.value.payload));
        scrollToBottom();
      }
    } else if (parsed.type === 'RunFinished') {
      if (currentSource) {
        currentSource.close();
        currentSource = null;
      }
    }
  }

  function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = '';

    if (currentSource) {
      currentSource.close();
      currentSource = null;
    }

    appendUserMessage(text);

    const url = '/agent/stream?message=' + encodeURIComponent(text);
    const source = new EventSource(url);
    currentSource = source;

    source.onmessage = function (e) {
      try {
        const parsed = JSON.parse(e.data);
        handleEvent(parsed);
      } catch (_) {
        // ignore malformed events
      }
    };

    source.onerror = function () {
      if (currentBubble) {
        const err = document.createElement('p');
        err.className = 'error';
        err.textContent = 'Connection error.';
        currentBubble.appendChild(err);
      }
      source.close();
      currentSource = null;
    };
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') sendMessage();
  });
}());
