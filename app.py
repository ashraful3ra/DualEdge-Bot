import os, json, time, threading, ssl
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from functools import wraps
from flask_socketio import SocketIO
from dotenv import load_dotenv
from utils.db import init_db, connect, now, to_dict
from utils.crypto import enc_str, dec_str
from utils.binance import BinanceUM
from cryptography.fernet import InvalidToken

load_dotenv(); init_db()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# --- START: PASSWORD PROTECTION ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        app_password = os.environ.get('APP_PASSWORD')
        if app_password and password == app_password:
            session['logged_in'] = True
            session.permanent = True
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid password!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# --- END: PASSWORD PROTECTION ---


#<editor-fold desc="Helper Functions">
def get_account(acc_id):
    with connect() as con:
        cur=con.cursor(); cur.execute('SELECT * FROM accounts WHERE id=?',(acc_id,)); r=cur.fetchone()
        return to_dict(r)

def safe_get_client(acc):
    try:
        api_key=dec_str(acc['api_key_enc']); api_secret=dec_str(acc['api_secret_enc'])
    except InvalidToken:
        raise RuntimeError("Encryption key mismatch. Please re-add account with a fixed ENCRYPTION_KEY.")
    return BinanceUM(api_key, api_secret, bool(acc['testnet']))

def list_accounts():
    with connect() as con:
        cur=con.cursor(); cur.execute('SELECT * FROM accounts ORDER BY id DESC')
        return [to_dict(r) for r in cur.fetchall()]

def list_templates():
    with connect() as con:
        cur=con.cursor(); cur.execute('SELECT * FROM templates ORDER BY id DESC')
        out=[]
        for r in cur.fetchall():
            d=to_dict(r); d['r_points']=json.loads(d['r_points_json'] or '[]'); out.append(d)
        return out

def list_bots(limit=5, offset=0):
    with connect() as con:
        cur = con.cursor()
        cur.execute('SELECT b.*, a.name as account_name FROM bots b LEFT JOIN accounts a ON a.id=b.account_id ORDER BY b.id DESC LIMIT ? OFFSET ?', (limit, offset))
        out = []
        for r in cur.fetchall():
            d = to_dict(r)
            if not d.get('account_name'):
                d['account_name'] = 'Account Deleted'
            d['r_points'] = json.loads(d['r_points_json'] or '[]')
            
            d['long_roi'] = d.get('long_final_roi', 0.0) if 'Closed' in d.get('long_status', '') else 0.0
            d['short_roi'] = d.get('short_final_roi', 0.0) if 'Closed' in d.get('short_status', '') else 0.0
            
            d['mark_price'] = None
            out.append(d)
        return out
#</editor-fold>

#<editor-fold desc="App Routes (UI)">
@app.route('/')
@login_required
def home(): return redirect(url_for('dashboard'))

def update_account_balances():
    accounts = list_accounts()
    for acc in accounts:
        try:
            bn = safe_get_client(acc)
            balance = bn.futures_balance()
            with connect() as con:
                cur = con.cursor()
                cur.execute('UPDATE accounts SET futures_balance=?, updated_at=? WHERE id=?', (balance, now(), acc['id']))
                con.commit()
        except Exception as e:
            print(f"Could not update balance for account {acc['name']}: {e}")

@app.route('/account')
@login_required
def account():
    update_account_balances()
    return render_template('account.html', accounts_json=json.dumps(list_accounts()))

@app.route('/dashboard')
@login_required
def dashboard():
    accts=list_accounts(); tpls=list_templates()
    return render_template('dashboard.html', accounts=accts, accounts_json=json.dumps(accts), templates_json=json.dumps(tpls))
#</editor-fold>

#<editor-fold desc="API Routes">
@app.route('/accounts/add', methods=['POST'])
def accounts_add():
    data=request.get_json(force=True); name=data.get('name','').strip()
    exchange=data.get('exchange','BINANCE_UM'); api_key=data.get('api_key','').strip(); api_secret=data.get('api_secret','').strip()
    testnet=1 if data.get('testnet') else 0
    if not name or not api_key or not api_secret: return jsonify({'error':'Missing fields'}),400
    try:
        bn=BinanceUM(api_key, api_secret, bool(testnet)); balance=bn.futures_balance(); bn.set_hedge_mode(True)
    except Exception as e:
        return jsonify({'error':str(e)}),400
    with connect() as con:
        cur=con.cursor(); cur.execute('INSERT INTO accounts (name,exchange,api_key_enc,api_secret_enc,testnet,active,futures_balance,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (name,exchange,enc_str(api_key),enc_str(api_secret),testnet,1,balance,now(),now())); con.commit()
    return jsonify({'ok':True,'accounts':list_accounts()})

@app.route('/accounts/toggle/<int:acc_id>', methods=['POST'])
def accounts_toggle(acc_id):
    with connect() as con:
        cur=con.cursor(); cur.execute('UPDATE accounts SET active = CASE active WHEN 1 THEN 0 ELSE 1 END, updated_at=? WHERE id=?',(now(),acc_id)); con.commit()
    return jsonify({'ok':True})

@app.route('/accounts/delete/<int:acc_id>', methods=['POST'])
def accounts_delete(acc_id):
    with connect() as con:
        cur=con.cursor(); cur.execute('DELETE FROM accounts WHERE id=?',(acc_id,)); con.commit()
    return jsonify({'ok':True,'accounts':list_accounts()})

@app.route('/api/symbol-info')
def symbol_info():
    symbol=(request.args.get('symbol') or '').upper().strip()
    if not symbol: return jsonify({'error':'symbol required'}),400
    bn=BinanceUM('','',False)
    try:
        lot,min_notional=bn.symbol_filters(symbol)
        out={'symbol':symbol,'min_notional':min_notional or 0,'lot':lot or {}}
        return jsonify(out)
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/futures/symbols')
def futures_symbols():
    bn=BinanceUM('', '', False)
    try:
        info=bn.exchange_info()
        symbols=[s['symbol'] for s in info.get('symbols',[]) if s.get('quoteAsset')=='USDT' and s.get('status')=='TRADING']
        return jsonify({'symbols':symbols})
    except Exception as e:
        return jsonify({'symbols':[],'error':str(e)}),500

@app.route('/templates/save', methods=['POST'])
def tpl_save():
    data=request.get_json(force=True); name=data.get('name','').strip()
    if not name: return jsonify({'error':'Name required'}),400
    with connect() as con:
        cur=con.cursor(); cur.execute('INSERT INTO templates (name,symbol,long_enabled,long_amount,long_leverage,short_enabled,short_amount,short_leverage,r_points_json,cond_sl_close,cond_trailing,cond_close_last,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (name,data.get('symbol','').upper(),int(bool(data.get('long_enabled'))),float(data.get('long_amount') or 0),int(data.get('long_leverage') or 1),
             int(bool(data.get('short_enabled'))),float(data.get('short_amount') or 0),int(data.get('short_leverage') or 1),
             json.dumps(data.get('r_points') or []),int(bool(data.get('cond_sl_close'))),int(bool(data.get('cond_trailing'))),int(bool(data.get('cond_close_last'))),now()))
        con.commit()
    return jsonify({'ok':True})

@app.route('/templates/list')
def tpl_list(): return jsonify({'items':list_templates()})

@app.route('/templates/get/<int:tpl_id>')
def tpl_get(tpl_id):
    with connect() as con:
        cur=con.cursor(); cur.execute('SELECT * FROM templates WHERE id=?',(tpl_id,)); r=cur.fetchone()
        if not r: return jsonify({'error':'Not found'}),404
        d=to_dict(r); d['r_points']=json.loads(d['r_points_json'] or '[]'); return jsonify(d)

@app.route('/templates/delete/<int:tpl_id>', methods=['POST'])
def tpl_delete(tpl_id):
    with connect() as con:
        cur=con.cursor(); cur.execute('DELETE FROM templates WHERE id=?',(tpl_id,)); con.commit()
    return jsonify({'ok':True})

@app.route('/bots/list')
def bots_list():
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 5))
    offset = (page - 1) * limit
    return jsonify({'items': list_bots(limit=limit, offset=offset)})

@app.route('/bots/submit', methods=['POST'])
def bots_submit():
    data=request.get_json(force=True)
    name=data.get('name','').strip(); symbol=data.get('symbol','').upper(); account_id=int(data.get('account_id') or 0)
    margin_mode = data.get('margin_mode', 'ISOLATED').upper()
    long_enabled=int(bool(data.get('long_enabled'))); short_enabled=int(bool(data.get('short_enabled')))
    long_leverage=int(data.get('long_leverage') or 0); short_leverage=int(data.get('short_leverage') or 0)
    long_amount=float(data.get('long_amount') or 0); short_amount=float(data.get('short_amount') or 0)
    r_points_raw=data.get('r_points', [])
    r_points = [p for p in r_points_raw if p is not None]
    cond_sl_close=int(bool(data.get('cond_sl_close'))); cond_trailing=int(bool(data.get('cond_trailing'))); cond_close_last=int(bool(data.get('cond_close_last')))
    
    if not name or not symbol or not account_id: return jsonify({'error':'Missing required fields'}),400
    if not long_enabled and not short_enabled: return jsonify({'error':'Enable Long and/or Short'}),400
    
    acc=get_account(account_id)
    if not acc or not acc['active']: return jsonify({'error':'Account not active'}),400
    
    try: bn=safe_get_client(acc)
    except RuntimeError as e: return jsonify({'error':str(e)}),400
    
    is_hedge_mode = bn.get_hedge_mode()

    try:
        lot, min_notional = bn.symbol_filters(symbol)
        minN = float(min_notional or 0)
        if long_enabled and long_amount < max(minN, 0): return jsonify({'error': f'Long amount (${long_amount}) is below min notional (${minN}).'}), 400
        if short_enabled and short_amount < max(minN, 0): return jsonify({'error': f'Short amount (${short_amount}) is below min notional (${minN}).'}), 400
        
        bn.set_margin_type(symbol, margin_mode)
        if long_enabled: bn.set_leverage(symbol, long_leverage)
        if short_enabled: bn.set_leverage(symbol, short_leverage)

    except Exception as e: return jsonify({'error': f'Failed to set margin/leverage: {e}'}), 400
    
    try: price=float(bn.price(symbol)['price'])
    except Exception as e: return jsonify({'error': f'Price fetch failed: {e}'}), 400
    
    long_entry=None; short_entry=None
    try:
        if long_enabled and long_amount > 0:
            qty=bn.round_lot_size(symbol, long_amount/price)
            position_side = 'LONG' if is_hedge_mode else 'BOTH'
            bn.order_market(symbol, 'BUY', qty, position_side)
            long_entry=price
        if short_enabled and short_amount > 0:
            qty=bn.round_lot_size(symbol, short_amount/price)
            position_side = 'SHORT' if is_hedge_mode else 'BOTH'
            bn.order_market(symbol, 'SELL', qty, position_side)
            short_entry=price
    except Exception as e: return jsonify({'error': f'Order place failed: {e}'}), 400
    
    entry_price = long_entry or short_entry
    if long_enabled and short_enabled:
        long_entry = entry_price
        short_entry = entry_price

    sl_point = None
    if cond_sl_close:
        sl_points = sorted([p for p in r_points if p < 0], reverse=True)
        if sl_points:
            sl_point = sl_points[0]

    with connect() as con:
        cur=con.cursor(); cur.execute('INSERT INTO bots (name, account_id, symbol, long_enabled, long_amount, long_leverage, short_enabled, short_amount, short_leverage, r_points_json, cond_sl_close, cond_trailing, cond_close_last, start_time, long_entry_price, short_entry_price, long_status, short_status, long_sl_point, short_sl_point, testnet, long_final_roi, short_final_roi) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (name,account_id,symbol,long_enabled,long_amount,long_leverage,short_enabled,short_amount,short_leverage,json.dumps(r_points),cond_sl_close,cond_trailing,cond_close_last,now(),long_entry,short_entry,'Running' if long_enabled and long_amount>0 else 'No trade','Running' if short_enabled and short_amount>0 else 'No trade',sl_point if long_enabled else None, sl_point if short_enabled else None, acc['testnet'],0.0,0.0))
        bot_id=cur.lastrowid; con.commit()
    
    start_roi_worker(bot_id)
    return jsonify({'ok':True,'bot_id':bot_id})

@app.route('/bots/close/<int:bot_id>', methods=['POST'])
def bots_close_route(bot_id):
    with connect() as con:
        cur=con.cursor(); cur.execute('SELECT * FROM bots WHERE id=?',(bot_id,)); r=cur.fetchone()
        if not r: return jsonify({'error':'Not found'}),404
        bot=to_dict(r)
    
    acc=get_account(bot['account_id'])
    try: bn=safe_get_client(acc)
    except RuntimeError as e: return jsonify({'error':str(e)}),400
    
    close_position(bot, 'LONG', bn)
    close_position(bot, 'SHORT', bn)
    
    return jsonify({'ok':True})
#</editor-fold>

#<editor-fold desc="Trading Logic and Websocket">
ROI_THREADS={}; ROI_LOCK=threading.Lock()

def compute_roi(entry, mark, lev, side):
    if not entry or entry <= 0: return 0.0
    if side == 'LONG':
        return ((mark - entry) / entry) * lev * 100.0
    else: # SHORT
        return ((entry - mark) / entry) * lev * 100.0

def close_position(bot, position_side_to_close, bn_client):
    symbol = bot['symbol']
    bot_id = bot['id']
    status_field = 'long_status' if position_side_to_close == 'LONG' else 'short_status'
    roi_field = 'long_final_roi' if position_side_to_close == 'LONG' else 'short_final_roi'

    with connect() as con:
        cur = con.cursor()
        current_status = cur.execute(f"SELECT {status_field} FROM bots WHERE id=?", (bot_id,)).fetchone()[0]
        if 'Closed' in current_status:
            return

    print(f"Attempting to close {position_side_to_close} position for bot {bot_id} on {symbol}")
    try:
        pos_risk = bn_client.position_risk(symbol)
        position_to_close = None

        for p in pos_risk:
            amt = float(p.get('positionAmt', 0))
            side = p.get('positionSide')

            if side == 'BOTH':
                if position_side_to_close == 'LONG' and amt > 0:
                    position_to_close = p
                    break
                if position_side_to_close == 'SHORT' and amt < 0:
                    position_to_close = p
                    break
            elif side == position_side_to_close and amt != 0:
                position_to_close = p
                break
        
        if position_to_close:
            qty_to_close = abs(float(position_to_close.get('positionAmt', 0)))
            is_hedge_mode = position_to_close.get('positionSide') != 'BOTH'
            order_side = 'SELL' if position_side_to_close == 'LONG' else 'BUY'
            
            if is_hedge_mode:
                bn_client.order_market(symbol, order_side, qty_to_close, position_side=position_side_to_close)
            else:
                bn_client.order_market(symbol, order_side, qty_to_close, reduce_only=True)

            time.sleep(1) 
            
            trades = bn_client.get_user_trades(symbol, start_time=int(bot['start_time'] * 1000) - 60000)
            pnl = 0.0
            
            for trade in reversed(trades):
                if float(trade['realizedPnl']) != 0 and trade['side'] == order_side and trade['positionSide'] == position_side_to_close:
                    pnl = float(trade['realizedPnl'])
                    break
            
            entry_amount = bot['long_amount'] if position_side_to_close == 'LONG' else bot['short_amount']
            leverage = bot['long_leverage'] if position_side_to_close == 'LONG' else bot['short_leverage']
            
            final_roe = 0.0
            if entry_amount > 0 and leverage > 0:
                margin_used = entry_amount / leverage
                if margin_used > 0:
                    final_roe = (pnl / margin_used) * 100.0

            with connect() as con:
                con.cursor().execute(f"UPDATE bots SET {status_field}='Closed', {roi_field}=? WHERE id=?", (final_roe, bot_id))
                con.commit()

            socketio.emit('bot_status_update', {'bot_id': bot_id})
            print(f"SUCCESS: Position {position_side_to_close} for bot {bot_id} confirmed closed with ROE: {final_roe:.2f}%")
        else:
            with connect() as con:
                con.cursor().execute(f"UPDATE bots SET {status_field}='Closed' WHERE id=?", (bot_id,))
                con.commit()
            socketio.emit('bot_status_update', {'bot_id': bot_id})
    except Exception as e:
        print(f"FAIL: Could not close {position_side_to_close} for bot {bot_id}. Reason: {e}")

def process_trade_logic(bot, bn_client, mark_price):
    r_points = json.loads(bot['r_points_json'] or '[]')
    sl_points = sorted([p for p in r_points if p < 0], reverse=True)
    tp_points = sorted([p for p in r_points if p > 0])
    
    if 'long_sl_point' not in bot: bot['long_sl_point'] = None
    if 'short_sl_point' not in bot: bot['short_sl_point'] = None

    with connect() as con:
        cur = con.cursor()
        # --- LONG ---
        if bot['long_status'] == 'Running' and bot['long_entry_price']:
            roi = compute_roi(bot['long_entry_price'], mark_price, bot['long_leverage'], 'LONG')

            if bot['cond_trailing'] and len(tp_points) > 1:
                potential_new_sl = None
                for i in range(len(tp_points) - 1, 0, -1):
                    if roi >= tp_points[i]:
                        potential_new_sl = tp_points[i-1]
                        break
                
                if potential_new_sl is not None:
                    current_sl = bot.get('long_sl_point')
                    if current_sl is None or potential_new_sl > current_sl:
                        cur.execute("UPDATE bots SET long_sl_point=? WHERE id=?", (potential_new_sl, bot['id']))
                        con.commit()
                        bot['long_sl_point'] = potential_new_sl

            current_sl = bot.get('long_sl_point')
            if current_sl is not None and roi <= current_sl:
                close_position(bot, 'LONG', bn_client)
                return

            if (bot['cond_sl_close'] and sl_points and roi <= sl_points[0]) or \
               (bot['cond_close_last'] and tp_points and roi >= tp_points[-1]):
                close_position(bot, 'LONG', bn_client)
                return

        # --- SHORT ---
        if bot['short_status'] == 'Running' and bot['short_entry_price']:
            roi = compute_roi(bot['short_entry_price'], mark_price, bot['short_leverage'], 'SHORT')

            if bot['cond_trailing'] and len(tp_points) > 1:
                potential_new_sl = None
                for i in range(len(tp_points) - 1, 0, -1):
                    if roi >= tp_points[i]:
                        potential_new_sl = tp_points[i-1]
                        break
                
                if potential_new_sl is not None:
                    current_sl = bot.get('short_sl_point')
                    if current_sl is None or potential_new_sl > current_sl:
                        cur.execute("UPDATE bots SET short_sl_point=? WHERE id=?", (potential_new_sl, bot['id']))
                        con.commit()
                        bot['short_sl_point'] = potential_new_sl
            
            current_sl = bot.get('short_sl_point')
            if current_sl is not None and roi <= current_sl:
                close_position(bot, 'SHORT', bn_client)
                return

            if (bot['cond_sl_close'] and sl_points and roi <= sl_points[0]) or \
               (bot['cond_close_last'] and tp_points and roi >= tp_points[-1]):
                close_position(bot, 'SHORT', bn_client)
                return

def start_roi_worker(bot_id):
    import websocket, json, time
    
    with connect() as con:
        r = con.cursor().execute('SELECT * FROM bots WHERE id=?',(bot_id,)).fetchone()
        if not r: return
        bot_data = to_dict(r)

    acc = get_account(bot_data['account_id'])
    bn = safe_get_client(acc)
    ws_url = f"{bn.ws_base}/{bot_data['symbol'].lower()}@markPrice"
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            mark = float(data.get('p') or data.get('markPrice') or 0)
            
            with connect() as con:
                r = con.cursor().execute("SELECT long_status, short_status, long_sl_point, short_sl_point FROM bots WHERE id=?", (bot_id,)).fetchone()
                if r: 
                    bot_data['long_status'] = r['long_status']
                    bot_data['short_status'] = r['short_status']
                    bot_data['long_sl_point'] = r['long_sl_point']
                    bot_data['short_sl_point'] = r['short_sl_point']

            lroi=0.0; sroi=0.0;
            if not bot_data['long_status'].startswith('Closed'):
                 process_trade_logic(bot_data, bn, mark)
                 lroi = compute_roi(bot_data.get('long_entry_price'), mark, bot_data.get('long_leverage'), 'LONG')
            if not bot_data['short_status'].startswith('Closed'):
                 process_trade_logic(bot_data, bn, mark)
                 sroi = compute_roi(bot_data.get('short_entry_price'), mark, bot_data.get('short_leverage'), 'SHORT')

            socketio.emit('bot_roi', {'bot_id': bot_id, 'mark_price': mark, 'long_roi': lroi, 'short_roi': sroi, 'long_sl_point': bot_data['long_sl_point'], 'short_sl_point': bot_data['short_sl_point']})
        except Exception as e:
            print(f"Error in on_message for bot {bot_id}: {e}")

    def on_error(ws, err):
        print(f"WS Error for bot {bot_id}: {err}")
    
    def on_close(ws, status_code, msg):
        print(f"WS Closed for bot {bot_id}. Status: {status_code}. Msg: {msg}. Reconnecting...")
        time.sleep(5)

    def run():
        while True:
            print(f"Attempting to connect WebSocket for bot {bot_id}...")
            try:
                ws = websocket.WebSocketApp(
                    ws_url, 
                    on_message=on_message, 
                    on_error=on_error, 
                    on_close=on_close
                )
                ws.run_forever(
                    ping_interval=20, 
                    ping_timeout=10,
                    sslopt={"cert_reqs": ssl.CERT_NONE}
                )
            except Exception as e:
                print(f"Websocket connection failed for bot {bot_id}: {e}")
                time.sleep(10)
            
    th = threading.Thread(target=run, daemon=True); th.start()
    with ROI_LOCK: ROI_THREADS[bot_id] = th
#</editor-fold>

def start_all_bot_workers():
    print("Starting workers for all active bots...")
    with connect() as con:
        for r in con.cursor().execute("SELECT id FROM bots WHERE long_status='Running' OR short_status='Running'").fetchall():
            bot_id = r['id']
            if bot_id not in ROI_THREADS:
                print(f"Starting worker for bot ID: {bot_id}")
                start_roi_worker(bot_id)

if __name__ == '__main__':
    start_all_bot_workers()
    host=os.environ.get('HOST','127.0.0.1'); port=int(os.environ.get('PORT','5000'))
    socketio.run(app, host=host, port=port)