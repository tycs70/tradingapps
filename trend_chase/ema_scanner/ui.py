"""Tk main-thread UI; only immutable coordinator snapshots reach the widgets."""
from datetime import datetime
from dataclasses import replace
import tkinter as tk
from tkinter import ttk, messagebox

from . import VERSION
from .broker import normalize_token
from .credentials import TokenStore
from .models import IST, Settings

BG='#101925'; PANEL='#172334'; TEXT='#e6edf5'; MUTED='#91a4bc'
BLUE='#57a6ff'; GREEN='#46d8a3'; RED='#ff8190'; GOLD='#f2c66f'


def plot_bounds(width,height):
    available_w=max(120,width-120);available_h=max(60,height-70)
    pw=min(available_w,2*available_h);ph=pw/2
    return 65+(available_w-pw)/2,25+(available_h-ph)/2,pw,ph


def fmt_time(value):
    return value.astimezone(IST).strftime('%H:%M:%S') if value else '—'


class App:
    def __init__(self,root,scanner,store,token_store=None):
        self.root,self.scanner,self.store=root,scanner,store
        self.token_store=token_store if token_store is not None else TokenStore(store.path.parent/'upstox-token.dpapi')
        self.settings=store.load();self.selected=None;self.current=None;self.after_id=None;self.closed=False
        self._event_count=0;self._last_event=None;self._event_sequence=0
        root.title(f'EMA Pre-Cross Scanner  ·  {VERSION}')
        root.geometry('1280x920');root.minsize(1050,760);root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self._style()
        self.token=tk.StringVar();self.filter=tk.StringVar(value='All')
        self.remember_token=tk.BooleanVar(value=self.settings.remember_token and self.token_store.available)
        self.token_status=tk.StringVar(value='Saved tokens still expire. Replace the token when Upstox requires it.')
        try:
            if self.remember_token.get():self.token.set(self.token_store.load() or '')
            elif not self.settings.remember_token:self.token_store.clear()
        except OSError:
            self.token_status.set('Saved token is unavailable. Paste a fresh token, or untick Remember token to forget it.')
        self.proximity=tk.StringVar(value=str(self.settings.proximity_pct))
        self.chart_bars=tk.StringVar(value=str(self.settings.chart_bars))
        self.angle_intervals=tk.StringVar(value=str(self.settings.angle_intervals))
        self.status=tk.StringVar(value='Disconnected');self.coverage=tk.StringVar();self.rule=tk.StringVar()
        self.chart_title=tk.StringVar(value='Select an ARMED stock, or choose any ready stock below')
        self.alerts=tk.BooleanVar(value=True)
        header=ttk.Frame(root,padding=(22,18));header.pack(fill='x')
        ttk.Label(header,text='EMA PRE-CROSS',style='Title.TLabel').pack(side='left')
        ttk.Label(header,text='  9 / 21   •   NSE stocks   •   5 MIN',style='Muted.TLabel').pack(side='left')
        self.connect_button=ttk.Button(header,text='Connect to Upstox',command=self.connect)
        self.connect_button.pack(side='right')
        ttk.Button(header,text='Disconnect',command=scanner.disconnect).pack(side='right',padx=8)
        status=ttk.Frame(root,padding=(22,0,22,12));status.pack(fill='x')
        ttk.Label(status,textvariable=self.status,foreground=BLUE).pack(anchor='w')
        ttk.Label(status,textvariable=self.coverage,style='Muted.TLabel').pack(anchor='w',pady=(4,0))
        self.tabs=ttk.Notebook(root);self.tabs.pack(fill='both',expand=True,padx=18,pady=(0,12))
        self.main=ttk.Frame(self.tabs,padding=12);self.tabs.add(self.main,text='  Scanner  ')
        self.event_tab=ttk.Frame(self.tabs,padding=12);self.tabs.add(self.event_tab,text='  Events  ')
        self.settings_tab=ttk.Frame(self.tabs,padding=20);self.tabs.add(self.settings_tab,text='  Settings & Upstox  ')
        self.diag_tab=ttk.Frame(self.tabs,padding=12);self.tabs.add(self.diag_tab,text='  Diagnostics  ')
        self._board();self._events();self._settings();self._diagnostics()
        ttk.Label(root,text='ARMED = provisional, before crossover. Signals concern shares; the app places no orders.',
                  style='Muted.TLabel',padding=(22,0,22,10)).pack(anchor='w')
        self.refresh()

    def _style(self):
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10),background=BG,foreground=TEXT)
        style.configure('Title.TLabel',font=('Segoe UI',20,'bold'),foreground=TEXT)
        style.configure('Muted.TLabel',foreground=MUTED)
        style.configure('TButton',padding=(12,7),background=PANEL,borderwidth=0)
        style.map('TButton',background=[('active','#253951')])
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',padding=(12,9),background=PANEL)
        style.map('TNotebook.Tab',background=[('selected','#263e58')])
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=29,borderwidth=0)
        style.configure('Treeview.Heading',background='#21324a',foreground=MUTED,font=('Segoe UI',9,'bold'),padding=7)
        style.map('Treeview',background=[('selected','#294b69')],foreground=[('selected',TEXT)])
        style.configure('TEntry',fieldbackground=PANEL,foreground=TEXT,insertcolor=TEXT,padding=6)
        style.configure('TCombobox',fieldbackground=PANEL,foreground=TEXT,arrowcolor=TEXT,padding=5)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])

    def _table(self,parent,columns,widths,height=9):
        holder=ttk.Frame(parent);holder.pack(fill='both',expand=True)
        tree=ttk.Treeview(holder,columns=columns,show='headings',height=height)
        for name,width in zip(columns,widths):
            tree.heading(name,text=name);tree.column(name,width=width,minwidth=45,anchor='center')
        v=ttk.Scrollbar(holder,orient='vertical',command=tree.yview)
        h=ttk.Scrollbar(holder,orient='horizontal',command=tree.xview)
        tree.configure(yscrollcommand=v.set,xscrollcommand=h.set)
        tree.grid(row=0,column=0,sticky='nsew');v.grid(row=0,column=1,sticky='ns');h.grid(row=1,column=0,sticky='ew')
        holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        return tree

    def _board(self):
        controls=ttk.Frame(self.main);controls.pack(fill='x',pady=(0,8))
        ttk.Label(controls,text='TOP 20 ARMED OPPORTUNITIES',font=('Segoe UI',11,'bold')).pack(side='left')
        ttk.Label(controls,textvariable=self.rule,style='Muted.TLabel').pack(side='left',padx=18)
        view=ttk.Combobox(controls,textvariable=self.filter,values=['All','Bullish','Bearish'],state='readonly',width=11)
        view.pack(side='right');view.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        board_holder=ttk.Frame(self.main);board_holder.pack(fill='both',expand=True)
        self.board=self._table(board_holder,['Rank','Stock','Side','State','EMA9 angle','EMA9','EMA21','Gap %','LTP','Quote (IST)','Armed (IST)'],
                               [48,100,70,82,105,90,90,75,90,100,100],height=8)
        self.board.tag_configure('LONG',foreground=GREEN);self.board.tag_configure('SHORT',foreground=RED)
        self.board.bind('<<TreeviewSelect>>',self._select_row)
        self.empty=ttk.Label(self.main,text='Connect with a current Upstox token to load and scan eligible stocks.',style='Muted.TLabel')
        self.empty.pack(anchor='w',pady=7)
        chart_controls=ttk.Frame(self.main);chart_controls.pack(fill='x',pady=(4,4))
        ttk.Label(chart_controls,textvariable=self.chart_title,font=('Segoe UI',11,'bold')).pack(side='left')
        self.stock_pick=ttk.Combobox(chart_controls,state='readonly',width=18)
        self.stock_pick.pack(side='right');self.stock_pick.bind('<<ComboboxSelected>>',self._select_pick)
        self.canvas=tk.Canvas(self.main,height=320,bg=PANEL,highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw_chart())
        ttk.Label(self.main,text='Reference angle: EMA9 chord · fixed 2:1 plot · held price scale · green EMA9 / blue EMA21',
                  style='Muted.TLabel').pack(anchor='w',pady=(6,0))

    def _events(self):
        ttk.Label(self.event_tab,text='Observed transitions. Initial observations are labelled; all times are IST.',style='Muted.TLabel').pack(anchor='w',pady=(0,10))
        self.event_table=self._table(self.event_tab,['Time (IST)','Stock','State','Side','Angle','Observation'],[100,110,105,75,80,650],height=16)
        self.event_table.tag_configure('LONG',foreground=GREEN);self.event_table.tag_configure('SHORT',foreground=RED)

    def _settings(self):
        ttk.Label(self.settings_tab,text='Upstox connection',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(self.settings_tab,text='Paste a current Upstox access token, or use the saved token below.',style='Muted.TLabel').pack(anchor='w',pady=8)
        self.token_entry=ttk.Entry(self.settings_tab,textvariable=self.token,show='•',width=75)
        self.token_entry.pack(anchor='w',fill='x')
        self.remember_check=ttk.Checkbutton(self.settings_tab,text='Remember token on this Windows account (encrypted)',
                                          variable=self.remember_token,command=self.remember_changed)
        self.remember_check.pack(anchor='w',pady=(10,4))
        if not self.token_store.available:
            self.remember_check.state(['disabled'])
            self.token_status.set('Remember token requires Windows. Connect with a pasted token on this system.')
        ttk.Label(self.settings_tab,textvariable=self.token_status,style='Muted.TLabel',wraplength=960).pack(anchor='w')
        ttk.Button(self.settings_tab,text='Connect',command=self.connect).pack(anchor='w',pady=12)
        ttk.Label(self.settings_tab,text='Trading rules',font=('Segoe UI',15,'bold')).pack(anchor='w',pady=(16,10))
        form=ttk.Frame(self.settings_tab);form.pack(anchor='w')
        for row,(label,var) in enumerate([('Maximum EMA gap as % of share price (0.001–0.5)',self.proximity),
                                          ('Reference chart candles (20–120)',self.chart_bars),
                                          ('EMA9 angle intervals (1–5)',self.angle_intervals)]):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=7)
            ttk.Entry(form,textvariable=var,width=12).grid(row=row,column=1,padx=20,pady=7)
        ttk.Button(self.settings_tab,text='Apply & save rules',command=self.apply_settings).pack(anchor='w',pady=12)
        ttk.Checkbutton(self.settings_tab,text='Sound for new live ARMED/crossover events',variable=self.alerts).pack(anchor='w',pady=6)
        text=('LONG: EMA9 below EMA21, rising and converging; positive chart angle; gap inside the limit.\n'
              'SHORT: EMA9 above EMA21, falling and converging; negative chart angle; same gap limit.\n\n'
              'The developing five-minute EMA is recalculated from the previous completed EMA on every quote.\n'
              'Rank uses current direction-aligned chart angle. No ATR enters the angle or ranking.\n'
              'The chart holds its scale during a candle unless prices breach it. External chart zoom can differ.\n'
              'Only fresh quotes during the normal NSE session qualify. Default proximity: 0.05%.')
        ttk.Label(self.settings_tab,text=text,style='Muted.TLabel',wraplength=960,justify='left').pack(anchor='w',pady=18)

    def _diagnostics(self):
        ttk.Label(self.diag_tab,text='Per-stock readiness. Missing history and stale quotes pause that stock independently.',style='Muted.TLabel').pack(anchor='w',pady=(0,10))
        self.stock_table=self._table(self.diag_tab,['Stock','Readiness','Reason'],[150,130,800],height=14)
        self.diag_text=tk.Text(self.diag_tab,height=6,bg=PANEL,fg=MUTED,relief='flat',font=('Consolas',10),wrap='word')
        self.diag_text.pack(fill='x',pady=(12,0))

    def connect(self):
        token=self.token.get().strip()
        if not token and self.remember_token.get():
            try:token=self.token_store.load() or ''
            except OSError:
                self.token_status.set('Saved token is unavailable. Paste a fresh token, or untick Remember token to forget it.')
        if not token:
            self.tabs.select(self.settings_tab);self.token_entry.focus_set();return
        try:
            token=normalize_token(token)
            if self.remember_token.get():
                self.token_store.save(token)
                self.token_status.set('Token saved with Windows encryption. It will be filled in on the next launch.')
            else:self.token_store.clear()
            settings=replace(self.settings,remember_token=self.remember_token.get())
            self.store.save(settings);self.settings=settings
            self.scanner.connect(token);self.token.set('');self.tabs.select(self.main)
        except ValueError as exc: messagebox.showerror('Upstox connection',str(exc),parent=self.root)
        except OSError:
            messagebox.showerror('Remember token','Unable to save or forget the token securely. Check your data-folder access, or untick Remember token and try again.',parent=self.root)
        self.refresh()

    def remember_changed(self):
        try:
            if not self.remember_token.get():self.token_store.clear()
            settings=replace(self.settings,remember_token=self.remember_token.get())
            self.store.save(settings);self.settings=settings
            self.token_status.set('Token will be encrypted and saved when you click Connect.' if settings.remember_token else
                                  'Saved token removed. Tokens are kept in memory unless you enable Remember token.')
        except OSError:
            self.remember_token.set(self.settings.remember_token)
            messagebox.showerror('Remember token','Unable to update the saved-token preference. Check your data-folder access.',parent=self.root)

    def apply_settings(self):
        try:
            settings=Settings(float(self.proximity.get()),int(self.chart_bars.get()),int(self.angle_intervals.get()),
                              remember_token=self.remember_token.get())
            self.store.save(settings);self.settings=settings;self.scanner.set_settings(settings)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Settings',str(exc) if isinstance(exc,ValueError) else 'Unable to save settings.',parent=self.root)
            return
        self.refresh()

    def _select_row(self,event=None):
        selected=self.board.selection()
        if selected:
            self.selected=selected[0];self.draw_chart()

    def _select_pick(self,event=None):
        symbol=self.stock_pick.get()
        if self.current:
            row=next((s for s in self.current['rows'] if s.symbol==symbol),None)
            if row:self.selected=row.key;self.draw_chart()

    def refresh(self):
        if self.closed:return
        if self.after_id:
            self.root.after_cancel(self.after_id);self.after_id=None
        data=self.scanner.snapshot();self.current=data
        self.status.set(data['status']+'   ·   NSE: '+data['market'])
        self.coverage.set('    '.join(f'{k.capitalize()}: {v}' for k,v in data['counts'].items()))
        settings=data['settings'];self.rule.set(f'Gap ≤ {settings.proximity_pct:g}%  ·  {settings.chart_bars}-candle reference')
        qualifying=[r for r in data['armed'] if self.filter.get()=='All' or r.side==('LONG' if self.filter.get()=='Bullish' else 'SHORT')]
        rows=qualifying[:20]
        existing=set(self.board.get_children());wanted={r.key for r in rows}
        for key in existing-wanted:self.board.delete(key)
        for rank,s in enumerate(rows,1):
            values=(rank,s.symbol,s.side,'ARMED',f'{s.angle:+.2f}°',f'{s.ema9:.3f}',f'{s.ema21:.3f}',f'{s.gap_pct:.4f}',f'{s.price:.2f}',fmt_time(s.quote_time),fmt_time(s.armed_time))
            if s.key in existing:self.board.item(s.key,values=values,tags=(s.side,))
            else:self.board.insert('', 'end',iid=s.key,values=values,tags=(s.side,))
            self.board.move(s.key,'',rank-1)
        if not self.selected and rows:self.selected=rows[0].key
        self.empty.configure(text=f'Showing {len(rows)} of {len(qualifying)} fresh ARMED setup(s). Ranked by current EMA9 chart angle.' if rows else
                             ('No fresh ARMED setups. Check coverage and Diagnostics.' if data['connected'] else 'Connect with a current Upstox token to load and scan eligible stocks.'))
        self.stock_pick.configure(values=sorted(s.symbol for s in data['rows']))
        events=data['events'][-300:]
        signature=events[-1] if events else None
        if signature!=self._last_event:
            self.event_table.delete(*self.event_table.get_children())
            for event in reversed(events):
                self.event_table.insert('','end',values=(fmt_time(event.time),event.symbol,event.state,event.side,f'{event.angle:+.2f}°',event.reason),tags=(event.side,))
            self._last_event=signature
        new_events=[e for e in data['events'] if e.sequence>self._event_sequence]
        if new_events:
            if self.alerts.get() and data['connected'] and any(not e.initial and e.state in ('ARMED','CROSSED') for e in new_events):
                self.root.bell()
            self._event_sequence=max(e.sequence for e in new_events)
        self.stock_table.delete(*self.stock_table.get_children())
        for symbol,ready,reason in data['stocks']:
            self.stock_table.insert('','end',values=(symbol,'READY' if ready else 'PAUSED',reason))
        self.diag_text.configure(state='normal');self.diag_text.delete('1.0','end')
        self.diag_text.insert('end','\n'.join(data['diagnostics'][-30:]));self.diag_text.configure(state='disabled')
        self.draw_chart();self.after_id=self.root.after(1000,self.refresh)

    def draw_chart(self):
        if self.closed:return
        canvas=self.canvas;canvas.delete('all')
        width,height=max(canvas.winfo_width(),200),max(canvas.winfo_height(),100)
        row=next((r for r in self.current['rows'] if r.key==self.selected),None) if self.current else None
        if not row:
            canvas.create_text(width/2,height/2,text='A fresh stock chart appears after connection and history validation.',fill=MUTED,font=('Segoe UI',12))
            self.chart_title.set('Reference chart · waiting for a fresh selection');return
        self.chart_title.set(f'{row.symbol}   {row.state} {row.side}   ·   EMA9 {row.angle:+.2f}°   ·   gap {row.gap_pct:.4f}%')
        self.stock_pick.set(row.symbol)
        x,y,pw,ph=plot_bounds(width,height)
        def point(i,price):
            xx,yy=row.scale.point(i,price,pw,ph);return x+xx,y+yy
        for i in range(5):
            yy=y+ph*i/4
            price=row.scale.maximum-(row.scale.maximum-row.scale.minimum)*i/4
            canvas.create_line(x,yy,x+pw,yy,fill='#25344a')
            canvas.create_text(x-8,yy,text=f'{price:.2f}',anchor='e',fill=MUTED,font=('Segoe UI',9))
        cw=max(2,min(8,pw/max(1,len(row.candles)-1)*.5))
        for i,c in enumerate(row.candles):
            xx,yhi=point(i,c.high);_,ylo=point(i,c.low);_,yo=point(i,c.open);_,yc=point(i,c.close)
            color=GREEN if c.close>=c.open else RED
            canvas.create_line(xx,yhi,xx,ylo,fill=color)
            canvas.create_rectangle(xx-cw/2,min(yo,yc),xx+cw/2,max(yo,yc)+1,outline=color,
                                    fill=PANEL if i==len(row.candles)-1 else color)
        for series,color,tag in [(row.ema21_points,BLUE,'ema21'),(row.ema9_points,GREEN,'ema9')]:
            coords=[coord for i,v in enumerate(series) for coord in point(i,v)]
            canvas.create_line(*coords,fill=color,width=2,tags=(tag,))
        intervals=self.current['settings'].angle_intervals
        start=len(row.ema9_points)-1-intervals;end=len(row.ema9_points)-1
        a=point(start,row.ema9_points[start]);b=point(end,row.ema9_points[end])
        canvas.create_line(*a,*b,fill=GOLD,width=3,tags=('measured_chord',))
        canvas.create_oval(b[0]-3,b[1]-3,b[0]+3,b[1]+3,fill=GOLD,outline=GOLD)
        for i in sorted(set([0,len(row.candles)//2,len(row.candles)-1])):
            xx,_=point(i,row.candles[i].close)
            canvas.create_text(xx,y+ph+17,text=row.candles[i].time.astimezone(IST).strftime('%d %b %H:%M'),fill=MUTED,font=('Segoe UI',9))
        canvas.create_text(x+8,y+12,anchor='w',text='EMA9    EMA21    Gold: angle chord    Hollow: forming / observed OHLC',fill=MUTED,font=('Segoe UI',9))

    def close(self):
        if self.closed:return
        self.closed=True;self.token.set('')
        if self.after_id:self.root.after_cancel(self.after_id)
        self.scanner.close();self.root.destroy()
