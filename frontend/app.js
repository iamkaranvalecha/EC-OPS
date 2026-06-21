(function () {
  var TOKEN_KEY = 'ecops_token';
  var USERNAME_KEY = 'ecops_username';

  // ── DOM refs ────────────────────────────────────────────────────────────────

  var loginScreen    = document.getElementById('login-screen');
  var chatContainer  = document.getElementById('chat-container');
  var loginForm      = document.getElementById('login-form');
  var loginError     = document.getElementById('login-error');
  var loginBtn       = document.getElementById('login-btn');
  var usernameInput  = document.getElementById('username');
  var passwordInput  = document.getElementById('password');
  var headerUsername = document.getElementById('header-username');
  var logoutBtn      = document.getElementById('logout-btn');
  var messagesEl     = document.getElementById('messages');
  var inputEl        = document.getElementById('message-input');
  var sendBtn        = document.getElementById('send-btn');

  var currentBubble = null;
  var currentSource = null;

  function setStreaming(active) {
    sendBtn.disabled = active;
    inputEl.disabled = active;
    sendBtn.textContent = active ? '…' : 'Send';
  }

  // ── Auth state ───────────────────────────────────────────────────────────────

  function getToken()    { return localStorage.getItem(TOKEN_KEY); }
  function getUsername() { return localStorage.getItem(USERNAME_KEY); }

  function saveToken(token, username) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, username);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
  }

  function showChat(username) {
    headerUsername.textContent = username;
    loginScreen.classList.add('hidden');
    chatContainer.classList.remove('hidden');
    inputEl.focus();
  }

  function showLogin(errorMsg) {
    chatContainer.classList.add('hidden');
    loginScreen.classList.remove('hidden');
    loginError.textContent = errorMsg || '';
    passwordInput.value = '';
    usernameInput.focus();
  }

  // ── Login ────────────────────────────────────────────────────────────────────

  loginForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var username = usernameInput.value.trim();
    var password = passwordInput.value;
    if (!username || !password) return;

    loginBtn.disabled = true;
    loginBtn.textContent = 'Signing in…';
    loginError.textContent = '';

    var body = 'username=' + encodeURIComponent(username)
             + '&password=' + encodeURIComponent(password);

    fetch('/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body,
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (d) {
            throw new Error(d.detail || 'Login failed');
          });
        }
        return res.json();
      })
      .then(function (data) {
        saveToken(data.access_token, username);
        showChat(username);
      })
      .catch(function (err) {
        loginError.textContent = err.message || 'Login failed';
      })
      .finally(function () {
        loginBtn.disabled = false;
        loginBtn.textContent = 'Sign in';
      });
  });

  // ── Logout ───────────────────────────────────────────────────────────────────

  logoutBtn.addEventListener('click', function () {
    if (currentSource) { currentSource.close(); currentSource = null; }
    clearToken();
    showLogin();
  });

  // ── Chat helpers ─────────────────────────────────────────────────────────────

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendUserMessage(text) {
    var div = document.createElement('div');
    div.className = 'message user';
    var p = document.createElement('p');
    p.textContent = text;
    div.appendChild(p);
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function createAgentBubble() {
    var div = document.createElement('div');
    div.className = 'message agent';
    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  function renderOrderCard(payload) {
    var card = document.createElement('div');
    card.className = 'order-card';

    var header = document.createElement('div');
    header.className = 'order-card-header';

    var idSpan = document.createElement('span');
    idSpan.className = 'order-id';
    idSpan.textContent = 'Order #' + (payload.id || '').slice(0, 8);

    var statusSpan = document.createElement('span');
    var statusLower = (payload.status || '').toLowerCase();
    statusSpan.className = 'status-badge status-' + statusLower;
    statusSpan.textContent = payload.status || '';

    header.appendChild(idSpan);
    header.appendChild(statusSpan);

    var body = document.createElement('div');
    body.className = 'order-card-body';

    var customer = document.createElement('p');
    customer.className = 'customer';
    customer.innerHTML = '<strong>Customer:</strong> ' + escapeHtml(payload.customer_name || '');

    var ul = document.createElement('ul');
    ul.className = 'items-list';
    (payload.items || []).forEach(function (item) {
      var li = document.createElement('li');
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

  // ── SSE event handler ────────────────────────────────────────────────────────

  function handleEvent(parsed) {
    if (parsed.type === 'RunStarted') {
      currentBubble = createAgentBubble();
      setStreaming(true);
    } else if (parsed.type === 'TextDelta') {
      if (currentBubble) {
        currentBubble.appendChild(document.createTextNode(parsed.delta));
        scrollToBottom();
      }
    } else if (parsed.type === 'ToolCallStart') {
      if (currentBubble) {
        var badge = document.createElement('span');
        badge.className = 'badge tool-start';
        badge.textContent = '🔧 calling ' + parsed.tool_name;
        currentBubble.appendChild(badge);
        scrollToBottom();
      }
    } else if (parsed.type === 'ToolCallResult') {
      if (currentBubble) {
        var badge = document.createElement('span');
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
      setStreaming(false);
      inputEl.focus();
    }
  }

  // ── Send message ─────────────────────────────────────────────────────────────

  function sendMessage() {
    if (sendBtn.disabled) return;
    var text = inputEl.value.trim();
    if (!text) return;

    var token = getToken();
    if (!token) { showLogin('Session expired — please sign in again.'); return; }

    inputEl.value = '';
    if (currentSource) { currentSource.close(); currentSource = null; }

    appendUserMessage(text);

    // EventSource can't set headers, so pass the token as a query param.
    // The backend _resolve_token() accepts both Authorization header and ?token=.
    var url = '/agent/stream?message=' + encodeURIComponent(text)
            + '&token=' + encodeURIComponent(token);
    var source = new EventSource(url);
    currentSource = source;

    source.onmessage = function (e) {
      try {
        handleEvent(JSON.parse(e.data));
      } catch (_) {
        // ignore malformed events
      }
    };

    source.onerror = function () {
      if (currentBubble) {
        // A 401 from the server causes an immediate onerror with no retry.
        // Check if token is still present; if so, it may have expired.
        var err = document.createElement('p');
        err.className = 'error';
        var tok = getToken();
        if (!tok) {
          err.textContent = 'Not authenticated.';
        } else {
          err.textContent = 'Connection error — your session may have expired.';
          clearToken();
          setTimeout(function () { showLogin('Session expired — please sign in again.'); }, 1500);
        }
        currentBubble.appendChild(err);
      }
      source.close();
      currentSource = null;
      setStreaming(false);
      inputEl.focus();
    };
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') sendMessage();
  });

  // ── Boot ─────────────────────────────────────────────────────────────────────

  var savedToken    = getToken();
  var savedUsername = getUsername();
  if (savedToken && savedUsername) {
    showChat(savedUsername);
  } else {
    showLogin();
  }

}());
