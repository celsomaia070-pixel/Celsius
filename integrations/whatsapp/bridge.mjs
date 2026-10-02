// Private JSON-lines transport. No HTTP port and no message/credential logging.
import makeWASocket, { DisconnectReason, jidNormalizedUser, useMultiFileAuthState,
  makeCacheableSignalKeyStore, Browsers } from '@whiskeysockets/baileys';
import pino from 'pino';
import readline from 'node:readline';

const emit = event => process.stdout.write(JSON.stringify(event) + '\n');
const logger = pino({ level: 'silent' });
const contacts = new Map();
const outgoing = new Set();
let socket;
let stopping = false;
let retries = 0;
let connected = false;
const startedAt = Math.floor(Date.now() / 1000);

function saveContacts(items) {
  for (const contact of items || []) {
    const id = jidNormalizedUser(contact.id || '');
    if (id && !id.endsWith('@g.us')) contacts.set(id, { ...contacts.get(id), ...contact, id });
  }
}
function selfIds() {
  return [socket?.user?.id, socket?.user?.lid].filter(Boolean).map(jidNormalizedUser);
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(process.argv[2]);
  socket = makeWASocket({
    auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, logger) },
    logger, browser: Browsers.ubuntu('Celsius'), syncFullHistory: false,
    markOnlineOnConnect: false,
    shouldIgnoreJid: jid => jid.endsWith('@g.us') || jid.endsWith('@broadcast') || jid.endsWith('@newsletter'),
  });
  socket.ev.on('creds.update', saveCreds);
  socket.ev.on('contacts.upsert', saveContacts);
  socket.ev.on('contacts.update', saveContacts);
  socket.ev.on('messaging-history.set', event => saveContacts(event.contacts));
  socket.ev.on('connection.update', update => {
    if (update.qr) emit({ type: 'qr', qr: update.qr });
    if (update.connection === 'open') {
      connected = true;
      retries = 0;
      emit({ type: 'connected', self_ids: selfIds() });
    }
    if (update.connection === 'close') {
      connected = false;
      const code = update.lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        stopping = true;
        emit({ type: 'logged_out' });
        process.exitCode = 0;
        process.stdin.destroy();
      } else if (!stopping) {
        emit({ type: 'reconnecting', code });
        setTimeout(() => start().catch(fatal), Math.min(30000, 1000 * 2 ** Math.min(retries++, 5)));
      }
    }
  });
  socket.ev.on('messages.upsert', update => {
    // Never turn restored history, groups, or somebody else's message into a command.
    if (!['notify', 'append'].includes(update.type)) return;
    for (const msg of update.messages || []) {
      if (Number(msg.messageTimestamp || 0) < startedAt) continue;
      const primaryJid = jidNormalizedUser(msg.key?.remoteJid || '');
      const alternateJid = jidNormalizedUser(msg.key?.remoteJidAlt || '');
      const jid = selfIds().includes(primaryJid) ? primaryJid : alternateJid;
      if (!msg.key?.fromMe || !selfIds().includes(jid) || outgoing.has(msg.key.id)) continue;
      const content = msg.message?.ephemeralMessage?.message || msg.message;
      const text = content?.conversation || content?.extendedTextMessage?.text || '';
      if (!text || text.startsWith('Celsius\n')) continue;
      emit({ type: 'message', id: msg.key.id, jid, from_me: true, text, self_ids: selfIds() });
    }
  });
}

function fatal() {
  emit({ type: 'error', message: 'Não foi possível conectar ao WhatsApp. Tente conectar novamente.' });
  process.exitCode = 1;
  process.stdin.destroy();
}

async function command(request) {
  try {
    if (!connected && !['stop', 'logout'].includes(request.action)) throw new Error('WhatsApp desconectado.');
    let result = {};
    if (request.action === 'send') {
      const content = request.path ? { document: { url: request.path }, mimetype: request.mime,
        fileName: request.name, caption: request.text || '' } : { text: request.text };
      const sent = await socket.sendMessage(request.jid, content);
      outgoing.add(sent.key.id);
      if (outgoing.size > 2048) outgoing.delete(outgoing.values().next().value);
      result = { message_id: sent.key.id };
    } else if (request.action === 'resolve') {
      const query = String(request.contact || '').trim();
      const digits = query.replace(/\D/g, '');
      if (/^[+\d ()-]+$/.test(query) && digits.length >= 10 && digits.length <= 15) {
        const entries = await socket.onWhatsApp(digits);
        result = { matches: (entries || []).filter(item => item.exists).map(item => ({ jid: item.jid, name: digits })) };
      } else {
        const normalized = query.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
        const matches = [...contacts.values()].filter(item => [item.name, item.notify, item.verifiedName]
          .some(name => name && name.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase() === normalized));
        result = { matches: matches.map(item => ({ jid: item.id, name: item.name || item.notify || query })).slice(0, 10) };
      }
    } else if (request.action === 'logout') {
      stopping = true;
      await socket?.logout();
    } else if (request.action === 'stop') {
      stopping = true;
      socket?.end(undefined);
    } else throw new Error('Comando de conexão desconhecido.');
    emit({ type: 'result', request_id: request.id, ok: true, result });
    if (stopping) process.exit(0);
  } catch (error) {
    emit({ type: 'result', request_id: request.id, ok: false, error: error.message });
  }
}

readline.createInterface({ input: process.stdin }).on('line', line => {
  try { void command(JSON.parse(line)); } catch { /* malformed private input */ }
}).on('close', () => {
  stopping = true;
  socket?.end(undefined);
  process.exit(0);
});
process.on('SIGTERM', () => { stopping = true; socket?.end(undefined); process.exit(0); });
start().catch(fatal);
