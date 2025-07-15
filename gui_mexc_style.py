import os, json, requests, threading, webbrowser
import tkinter as tk
from tkinter import ttk
from datetime import datetime, date

# API endpoints
API_24H = "https://api.mexc.com/api/v3/ticker/24hr"
API_KLINES = "https://api.mexc.com/api/v3/klines"

# File paths
data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
state_file = os.path.join(data_dir, 'trade_state.json')
log_file = os.path.join(data_dir, f"trade_log_{date.today()}.txt")

os.makedirs(data_dir, exist_ok=True)

# Rocket.Chat configuration
ROCKETCHAT = {
    'server': 'https://48db67704058.ngrok-free.app',
    'user': 'caothu78',
    'pass': 'Namhk555'
}
session = requests.Session()
rc_token = rc_uid = ''

def rocket_login():
    global rc_token, rc_uid
    try:
        resp = session.post(
            f"{ROCKETCHAT['server']}/api/v1/login",
            json={'username': ROCKETCHAT['user'], 'password': ROCKETCHAT['pass']},
            timeout=5
        ).json()
        data = resp.get('data')
        if data:
            rc_token = data.get('authToken')
            rc_uid = data.get('userId')
            session.headers.update({'X-Auth-Token': rc_token, 'X-User-Id': rc_uid})
        else:
            print(f"Rocket.Chat login failed: {resp}")
    except Exception as e:
        print(f"Rocket.Chat login error: {e}")

rocket_login()

# Load or initialize trade state
def load_state():
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except:
        return {}

trade_state = load_state()

top_list = []

# Initialize GUI
root = tk.Tk()
root.title("🚀 MEXC Spot Trade Tool")
root.geometry("1100x700")

# Top gainers table
ttk.Label(root, text="🟩 Top Tăng Spot", font=('Arial', 14, 'bold')).pack(pady=(10, 0))
frame_top = ttk.Frame(root)
frame_top.pack(fill='x', padx=10, pady=5)
scroll_top = ttk.Scrollbar(frame_top, orient='vertical')
tree_top = ttk.Treeview(
    frame_top,
    columns=('Coin','Giá','%24h','Range'),
    show='headings',
    height=10,
    yscrollcommand=scroll_top.set
)
scroll_top.config(command=tree_top.yview)
scroll_top.pack(side='right', fill='y')
tree_top.pack(fill='x')
for col in ('Coin','Giá','%24h','Range'):
    tree_top.heading(col, text=col)
    tree_top.column(col, anchor='center', width=120)
tree_top.bind('<Double-1>', lambda e: open_chart(tree_top))

# Lower trade table with Vietnamese headers
ttk.Label(root, text="🟦 Coin Đang Trade", font=('Arial', 14, 'bold')).pack(pady=(10, 0))
tree_trade = ttk.Treeview(
    root,
    columns=('Coin','Số tiền mua','Hiện có','Đã bán','Thu về'),
    show='headings',
    height=10
)
for col in ('Coin','Số tiền mua','Hiện có','Đã bán','Thu về'):
    tree_trade.heading(col, text=col)
    tree_trade.column(col, anchor='center', width=130)
tree_trade.pack(fill='x', padx=10, pady=5)
tree_trade.bind('<Double-1>', lambda e: open_chart(tree_trade))

# Controls
ctrl_frame = ttk.Frame(root)
ctrl_frame.pack(pady=10)
tk.Label(ctrl_frame, text='💰 Vốn (USDT):').pack(side='left')
cap_var = tk.StringVar(value='100')
tk.Entry(ctrl_frame, textvariable=cap_var, width=10).pack(side='left', padx=5)
tk.Button(ctrl_frame, text='🔄 Làm mới', command=lambda: [safe(refresh_top), safe(refresh_trade)]).pack(side='left')

# Helper functions
def open_chart(tree):
    sel = tree.selection()
    if sel:
        sym = tree.item(sel[0])['values'][0]
        webbrowser.open(f"https://www.mexc.com/exchange/{sym}_USDT?_from")

safe = lambda fn: threading.Thread(target=fn, daemon=True).start()
def format_price(p): return f"{p:.8f}".rstrip('0').rstrip('.')

def get_klines(symbol, interval, limit):
    url = f"{API_KLINES}?symbol={symbol}USDT&interval={interval}&limit={limit}"
    try:
        return session.get(url, timeout=5).json()
    except:
        return []

# Condition checks for Type A & B conditions
def passes_conditions(symbol):
    try:
        # 5m x3 >5%
        k5 = get_klines(symbol, '5m', 3)
        if len(k5)==3 and all((float(c[4])-float(c[1]))/float(c[1])*100>5 for c in k5):
            return True
        # 1m x5 >3%
        k1 = get_klines(symbol, '1m', 5)
        if len(k1)==5 and all((float(c[4])-float(c[1]))/float(c[1])*100>3 for c in k1):
            return True
    except:
        pass
    return False

# Refresh functions
def refresh_top():
    global top_list
    try:
        data = session.get(API_24H, timeout=10).json()
        top_list.clear()
        tree_top.delete(*tree_top.get_children())
        for d in data:
            if not d['symbol'].endswith('USDT'): continue
            open_p = float(d['openPrice'])
            if open_p <= 0: continue
            last_p = float(d['lastPrice'])
            pct = (last_p - open_p) / open_p * 100
            low_p = float(d['lowPrice'])
            high_p = float(d['highPrice'])
            rng = (high_p - low_p) / low_p * 100 if low_p>0 else 0
            if pct >= 40:
                sym = d['symbol'].replace('USDT','')
                top_list.append((sym, last_p))
                tree_top.insert('', 'end', values=(sym, format_price(last_p), f"{pct:.2f}%", f"{rng:.2f}%"))
    except Exception as e:
        print(f"refresh_top error: {e}")


def refresh_trade():
    try:
        cap = float(cap_var.get())
    except:
        cap = 100.0
    # Buy logic
    for sym, price in top_list:
        if sym not in trade_state and passes_conditions(sym):
            qty = round((cap * 0.1) / price, 6)
            trade_state[sym] = {'buy_price': price, 'qty': qty, 'notified_pct': 0}
            send_rocket(sym, f"🛒 MUA {sym} tại {format_price(price)} USDT – 10% vốn\n🔗 https://www.mexc.com/exchange/{sym}_USDT?_from")
    # Update table & sell logic
    tree_trade.delete(*tree_trade.get_children())
    for sym, rec in list(trade_state.items()):
        last = next((p for s, p in top_list if s==sym), rec['buy_price'])
        buy_total = rec['buy_price'] * rec['qty']
        current_total = last * rec['qty']
        pnl = (last - rec['buy_price'])/rec['buy_price']*100
        # notify 5%
        if pnl - rec['notified_pct'] >= 5:
            send_rocket(sym, f"📈 {sym} lời {pnl:.2f}% – hiện tại {format_price(last)} USDT")
            rec['notified_pct'] = pnl
        # sell if drop >20%
        if pnl <= -20:
            send_rocket(sym, f"🔻 BÁN {sym} do giảm >20%")
            with open(log_file, 'a') as f:
                f.write(f"{datetime.now()} | SELL {sym} | Buy:{format_price(rec['buy_price'])} | Sell:{format_price(last)} | Qty:{rec['qty']}\n")
            trade_state.pop(sym)
        else:
            # 'Đã bán' và 'Thu về' tạm để trống cho vị thế đang mở
            tree_trade.insert('', 'end', values=(
                sym,
                format_price(buy_total),
                format_price(current_total),
                '',
                ''
            ))
    # save state
    with open(state_file, 'w') as f:
        json.dump(trade_state, f, ensure_ascii=False, indent=2)

# Start loops
root.after(100, lambda: safe(refresh_top))
root.after(100, lambda: safe(refresh_trade))
root.mainloop()
