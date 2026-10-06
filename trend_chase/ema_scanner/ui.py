"""Tk main-thread UI; only immutable coordinator snapshots reach the widgets."""
from datetime import datetime
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont

from . import VERSION
from .broker import normalize_token
from .credentials import TokenStore
from .models import IST, Settings
from .demo import sample_data

BG='#101925'; PANEL='#172334'; TEXT='#e6edf5'; MUTED='#91a4bc'
BLUE='#57a6ff'; GREEN='#46d8a3'; RED='#ff8190'; GOLD='#f2c66f'


def plot_bounds(width,height):
    available_w=max(120,width-120);available_h=max(60,height-70)
    pw=min(available_w,2*available_h);ph=pw/2
    return 65+(available_w-pw)/2,25+(available_h-ph)/2,pw,ph


def fmt_time(value):
    return value.astimezone(IST).strftime('%H:%M:%S') if value else '—'


class App:
    def __init__(self,root,scanner,store,token_store=None,demo_mode=False):
        self.root,self.scanner,self.store=root,scanner,store
        self.demo_mode=demo_mode
        self.token_store=token_store if token_store is not None else TokenStore(store.path.parent/'upstox-token.dpapi')
        self.settings=Settings() if demo_mode else store.load()
        self.selected=None;self.current=None;self.after_id=None;self.closed=False
        self._event_count=0;self._last_event=None;self._event_sequence=0
        root.title(f'Trend Chase Version 1  ·  {VERSION}')
        width=min(1360,max(1050,root.winfo_screenwidth()-80))
        height=min(980,max(680,root.winfo_screenheight()-100))
        root.geometry(f'{width}x{height}');root.minsize(1050,680);root.configure(bg=BG)
        assets=Path(__file__).resolve().parent.parent/'assets'
        try:
            if (assets/'trend-chase.png').exists():
                self._icon=tk.PhotoImage(file=str(assets/'trend-chase.png'));root.iconphoto(True,self._icon)
            if (assets/'trend-chase.ico').exists() and root.tk.call('tk','windowingsystem')=='win32':
                root.iconbitmap(str(assets/'trend-chase.ico'))
        except tk.TclError:pass
        root.protocol('WM_DELETE_WINDOW',self.close)
        self._style()
        self.token=tk.StringVar();self.filter=tk.StringVar(value='All')
        self.remember_token=tk.BooleanVar(value=self.settings.remember_token and self.token_store.available)
        self.token_status=tk.StringVar(value='Saved tokens still expire. Replace the token when Upstox requires it.')
        try:
            if not demo_mode:
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
        ttk.Label(header,text='TREND CHASE VERSION 1',style='Title.TLabel').pack(side='left')
        ttk.Label(header,text='  9 / 21  |  NSE stocks  |  5 MIN',style='Muted.TLabel').pack(side='left')
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
        self.demo_tab=ttk.Frame(self.tabs,padding=12);self.tabs.add(self.demo_tab,text='  Demo  ')
        self.main_body,self.main_viewport=self._scroll_panel(self.main)
        self.demo_body,self.demo_viewport=self._scroll_panel(self.demo_tab)
        root.bind('<MouseWheel>',self._scroll_tab)
        root.bind('<Button-4>',lambda event:self._scroll_tab(event,-1))
        root.bind('<Button-5>',lambda event:self._scroll_tab(event,1))
        self._board();self._events();self._settings();self._diagnostics();self._demo()
        if demo_mode:
            self.tabs.select(self.demo_tab);self.connect_button.state(['disabled'])
        ttk.Label(root,text='Trends rank by frozen crossover angle. ARMED = pre-cross setup. Shares only; the app places no orders.',
                  style='Muted.TLabel',padding=(22,0,22,10)).pack(anchor='w',side='bottom',before=self.tabs)
        self.refresh()

    def _scroll_panel(self,parent):
        viewport=tk.Canvas(parent,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(parent,orient='vertical',command=viewport.yview)
        scrollbar.pack(side='right',fill='y');viewport.pack(fill='both',expand=True)
        viewport.configure(yscrollcommand=scrollbar.set)
        body=ttk.Frame(viewport)
        window=viewport.create_window(0,0,window=body,anchor='nw')
        body.bind('<Configure>',lambda event:viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>',lambda event:viewport.itemconfigure(window,width=event.width))
        return body,viewport

    def _scroll_tab(self,event,units=None):
        selected=self.tabs.select()
        viewport=self.main_viewport if selected==str(self.main) else self.demo_viewport if selected==str(self.demo_tab) else None
        if viewport:
            if units is None:units=-1 if event.delta>0 else 1
            viewport.yview_scroll(units,'units')

    def _style(self):
        self.font_family='Segoe UI' if 'Segoe UI' in tkfont.families(self.root) else 'Helvetica'
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('.',font=(self.font_family,10),background=BG,foreground=TEXT)
        style.configure('Title.TLabel',font=(self.font_family,20,'bold'),foreground=TEXT)
        style.configure('Muted.TLabel',foreground=MUTED)
        style.configure('TButton',padding=(12,7),background=PANEL,borderwidth=0)
        style.map('TButton',background=[('active','#253951')])
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',padding=(12,9),background=PANEL)
        style.map('TNotebook.Tab',background=[('selected','#263e58')])
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=29,borderwidth=0)
        style.configure('Treeview.Heading',background='#21324a',foreground=MUTED,font=(self.font_family,9,'bold'),padding=7)
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
        self.bullish_board=self._trend_table(self.main_body,'TOP 5 BULLISH','LONG')
        self.bearish_board=self._trend_table(self.main_body,'TOP 5 BEARISH','SHORT')
        self.trend_summary=tk.StringVar()
        ttk.Label(self.main_body,textvariable=self.trend_summary,style='Muted.TLabel').pack(anchor='w',pady=(4,10))
        controls=ttk.Frame(self.main_body);controls.pack(fill='x',pady=(0,8))
        ttk.Label(controls,text='NORMAL PRE-CROSS · TOP 20 ARMED',font=(self.font_family,11,'bold')).pack(side='left')
        ttk.Label(controls,textvariable=self.rule,style='Muted.TLabel').pack(side='left',padx=18)
        view=ttk.Combobox(controls,textvariable=self.filter,values=['All','Bullish','Bearish'],state='readonly',width=11)
        view.pack(side='right');view.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        board_holder=ttk.Frame(self.main_body);board_holder.pack(fill='both',expand=True)
        self.board=self._table(board_holder,['Rank','Stock','Side','State','EMA9 angle','EMA9','EMA21','Gap %','LTP','Quote (IST)','Armed (IST)'],
                               [48,100,70,82,105,90,90,75,90,100,100],height=4)
        self.board.tag_configure('LONG',foreground=GREEN);self.board.tag_configure('SHORT',foreground=RED)
        self.board.bind('<<TreeviewSelect>>',self._select_row)
        self.empty=ttk.Label(self.main_body,text='Connect with a current Upstox token to load and scan eligible stocks.',style='Muted.TLabel')
        self.empty.pack(anchor='w',pady=7)
        chart_controls=ttk.Frame(self.main_body);chart_controls.pack(fill='x',pady=(4,4))
        self.show_chart=tk.BooleanVar(value=False)
        ttk.Checkbutton(chart_controls,text='Show Chart',variable=self.show_chart,command=self.toggle_chart).pack(side='left',padx=(0,16))
        ttk.Label(chart_controls,textvariable=self.chart_title,font=(self.font_family,11,'bold')).pack(side='left')
        self.stock_pick=ttk.Combobox(chart_controls,state='readonly',width=18)
        self.stock_pick.pack(side='right');self.stock_pick.bind('<<ComboboxSelected>>',self._select_pick)
        self.chart_frame=ttk.Frame(self.main_body)
        self.canvas=tk.Canvas(self.chart_frame,height=240,bg=PANEL,highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw_chart())
        ttk.Label(self.chart_frame,text='Reference angle: EMA9 chord · fixed 2:1 plot · held price scale · green EMA9 / blue EMA21',
                  style='Muted.TLabel').pack(anchor='w',pady=(6,0))

    def _trend_table(self,parent,title,side):
        ttk.Label(parent,text=title,font=(self.font_family,12,'bold'),foreground=GREEN if side=='LONG' else RED).pack(anchor='w',pady=(4,6))
        table=self._table(parent,['Rank','Share','Status','Cross angle','Current angle','EMA9','EMA21','LTP','Distance %','Cross time IST'],
                          [48,150,112,104,104,100,100,100,100,130],height=5)
        table.tag_configure(side,foreground=GREEN if side=='LONG' else RED)
        if parent is self.main_body:
            table.bind('<<TreeviewSelect>>',lambda event,t=table:self._select_trend(t))
        return table

    def _fill_trends(self,table,rows):
        table.delete(*table.get_children())
        for rank,row in enumerate(rows[:5],1):
            table.insert('','end',iid=row.key,values=(rank,row.symbol,row.status,f'{row.crossover_angle:+.2f}°',
                         f'{row.current_angle:+.2f}°',f'{row.ema9:.3f}',f'{row.ema21:.3f}',f'{row.price:.2f}',
                         f'{row.distance_pct:+.4f}',fmt_time(row.crossover_time)),tags=(row.side,))

    def _select_trend(self,table):
        if table.selection():self.selected=table.selection()[0];self.draw_chart()

    def toggle_chart(self):
        if self.show_chart.get():self.chart_frame.pack(fill='both',expand=True)
        else:self.chart_frame.pack_forget()
        self.draw_chart()

    def _demo(self):
        self.demo_data=sample_data()
        ttk.Label(self.demo_body,text='DEMO — SAMPLE DATA',font=(self.font_family,16,'bold'),foreground=GOLD).pack(anchor='w')
        ttk.Label(self.demo_body,text='7 October 2026 · fictional shares and prices · layout illustration, not market outcomes or predictions.',style='Muted.TLabel').pack(anchor='w',pady=(4,8))
        self.demo_bullish_board=self._trend_table(self.demo_body,'TOP 5 BULLISH','LONG')
        self.demo_bearish_board=self._trend_table(self.demo_body,'TOP 5 BEARISH','SHORT')
        for table,rows in [(self.demo_bullish_board,self.demo_data['trends_long']),(self.demo_bearish_board,self.demo_data['trends_short'])]:
            self._fill_trends(table,rows)
            table.bind('<<TreeviewSelect>>',lambda event,t=table:self._select_demo_row(t))
        ttk.Label(self.demo_body,text='NORMAL PRE-CROSS · SAMPLE ARMED SETUPS',font=(self.font_family,11,'bold')).pack(anchor='w',pady=(10,6))
        self.demo_normal_board=self._table(self.demo_body,['Share','Side','State','Current angle','EMA9','EMA21','LTP','Gap %'],[180,80,100,120,110,110,110,100],height=3)
        for row in self.demo_data['armed']:
            self.demo_normal_board.insert('','end',iid=row.key,values=(row.symbol,row.side,'ARMED',f'{row.angle:+.2f}°',f'{row.ema9:.3f}',f'{row.ema21:.3f}',f'{row.price:.2f}',f'{row.gap_pct:.4f}'))
        self.demo_normal_board.bind('<<TreeviewSelect>>',lambda event:self._select_demo_row(self.demo_normal_board))
        controls=ttk.Frame(self.demo_body);controls.pack(fill='x',pady=8)
        self.demo_show_chart=tk.BooleanVar(value=False)
        ttk.Checkbutton(controls,text='Show Chart',variable=self.demo_show_chart,command=self.toggle_demo_chart).pack(side='left')
        self.demo_chart_title=tk.StringVar(value='Sample reference chart')
        ttk.Label(controls,textvariable=self.demo_chart_title,style='Muted.TLabel').pack(side='left',padx=16)
        self.demo_stock_pick=ttk.Combobox(controls,state='readonly',values=[r.symbol for r in self.demo_data['rows']],width=22)
        self.demo_stock_pick.pack(side='right');self.demo_stock_pick.bind('<<ComboboxSelected>>',self._select_demo_pick)
        self.demo_selected=self.demo_data['rows'][0].key
        self.demo_chart_frame=ttk.Frame(self.demo_body)
        self.demo_canvas=tk.Canvas(self.demo_chart_frame,height=220,bg=PANEL,highlightthickness=0)
        self.demo_canvas.pack(fill='both',expand=True);self.demo_canvas.bind('<Configure>',lambda event:self.draw_demo_chart())
        self.draw_demo_chart()

    def toggle_demo_chart(self):
        if self.demo_show_chart.get():self.demo_chart_frame.pack(fill='both',expand=True)
        else:self.demo_chart_frame.pack_forget()
        self.draw_demo_chart()

    def _select_demo_row(self,table):
        if table.selection():self.demo_selected=table.selection()[0];self.draw_demo_chart()

    def _select_demo_pick(self,event=None):
        row=next((r for r in self.demo_data['rows'] if r.symbol==self.demo_stock_pick.get()),None)
        if row:self.demo_selected=row.key;self.draw_demo_chart()

    def draw_demo_chart(self):
        row=next((r for r in self.demo_data['rows'] if r.key==self.demo_selected),None)
        self._draw_chart(self.demo_canvas,row,self.demo_chart_title,self.demo_stock_pick,self.demo_data['settings'])

    def _events(self):
        ttk.Label(self.event_tab,text='Observed transitions. Initial observations are labelled; all times are IST.',style='Muted.TLabel').pack(anchor='w',pady=(0,10))
        self.event_table=self._table(self.event_tab,['Time (IST)','Stock','State','Side','Angle','Observation'],[100,110,105,75,80,650],height=16)
        self.event_table.tag_configure('LONG',foreground=GREEN);self.event_table.tag_configure('SHORT',foreground=RED)

    def _settings(self):
        ttk.Label(self.settings_tab,text='Upstox connection',font=(self.font_family,15,'bold')).pack(anchor='w')
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
        ttk.Button(self.settings_tab,text='Forget Token',command=self.forget_token).pack(anchor='w',pady=(0,8))
        ttk.Label(self.settings_tab,text='Trading rules',font=(self.font_family,15,'bold')).pack(anchor='w',pady=(16,10))
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
              'Trend rank freezes the observed crossover angle; current angle is displayed separately.\n'
              'Confirmed trends remain until a completed close across EMA9 or EMA reversal.\n'
              'Normal pre-cross rank uses current direction-aligned angle. No ATR enters either ranking.\n'
              'The chart holds its scale during a candle unless prices breach it. External chart zoom can differ.\n'
              'Only fresh quotes during the normal NSE session qualify. Default proximity: 0.05%.')
        ttk.Label(self.settings_tab,text=text,style='Muted.TLabel',wraplength=960,justify='left').pack(anchor='w',pady=18)

    def _diagnostics(self):
        ttk.Label(self.diag_tab,text='Per-stock readiness. Missing history and stale quotes pause that stock independently.',style='Muted.TLabel').pack(anchor='w',pady=(0,10))
        self.stock_table=self._table(self.diag_tab,['Stock','Readiness','Reason'],[150,130,800],height=14)
        self.diag_text=tk.Text(self.diag_tab,height=6,bg=PANEL,fg=MUTED,relief='flat',font=('Consolas',10),wrap='word')
        self.diag_text.pack(fill='x',pady=(12,0))

    def connect(self):
        if self.demo_mode:return
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
        if self.demo_mode:return
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
        if self.demo_mode:return
        try:
            settings=Settings(float(self.proximity.get()),int(self.chart_bars.get()),int(self.angle_intervals.get()),
                              remember_token=self.remember_token.get())
            self.store.save(settings);self.settings=settings;self.scanner.set_settings(settings)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Settings',str(exc) if isinstance(exc,ValueError) else 'Unable to save settings.',parent=self.root)
            return
        self.refresh()

    def forget_token(self):
        if self.demo_mode:return
        self.token.set('')
        try:
            self.token_store.clear()
            settings=replace(self.settings,remember_token=False)
            self.store.save(settings);self.settings=settings;self.remember_token.set(False)
            self.token_status.set('Saved token removed. Paste a new token to connect.')
        except OSError:
            messagebox.showerror('Forget Token','Unable to remove the saved token or save the preference. Check your data-folder access.',parent=self.root)

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
        self._fill_trends(self.bullish_board,data.get('trends_long',[]))
        self._fill_trends(self.bearish_board,data.get('trends_short',[]))
        counts=data.get('trend_counts',{})
        self.trend_summary.set(f"Active bullish: {counts.get('active_long',0)}   ·   Active bearish: {counts.get('active_short',0)}   ·   Hidden pending fresh quotes / history: {counts.get('hidden',0)}")
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
            if not self.demo_mode and self.tabs.select()!=str(self.demo_tab) and self.alerts.get() and data['connected'] and any(not e.initial and e.state in ('ARMED','CROSSED') for e in new_events):
                self.root.bell()
            self._event_sequence=max(e.sequence for e in new_events)
        self.stock_table.delete(*self.stock_table.get_children())
        for symbol,ready,reason in data['stocks']:
            self.stock_table.insert('','end',values=(symbol,'READY' if ready else 'PAUSED',reason))
        self.diag_text.configure(state='normal');self.diag_text.delete('1.0','end')
        self.diag_text.insert('end',data.get('trend_status','')+'\n'+'\n'.join(data['diagnostics'][-30:]));self.diag_text.configure(state='disabled')
        self.draw_chart();self.after_id=self.root.after(1000,self.refresh)

    def draw_chart(self):
        if self.closed:return
        row=next((r for r in self.current['rows'] if r.key==self.selected),None) if self.current else None
        self._draw_chart(self.canvas,row,self.chart_title,self.stock_pick,self.current['settings'] if self.current else self.settings)

    def _draw_chart(self,canvas,row,title,pick,settings):
        if self.closed:return
        canvas.delete('all')
        width,height=max(canvas.winfo_width(),200),max(canvas.winfo_height(),100)
        if not row:
            canvas.create_text(width/2,height/2,text='A fresh stock chart appears after connection and history validation.',fill=MUTED,font=(self.font_family,12))
            title.set('Reference chart · waiting for a fresh selection');return
        title.set(f'{row.symbol}   {row.state} {row.side}   ·   EMA9 {row.angle:+.2f}°   ·   gap {row.gap_pct:.4f}%')
        pick.set(row.symbol)
        x,y,pw,ph=plot_bounds(width,height)
        def point(i,price):
            xx,yy=row.scale.point(i,price,pw,ph);return x+xx,y+yy
        for i in range(5):
            yy=y+ph*i/4
            price=row.scale.maximum-(row.scale.maximum-row.scale.minimum)*i/4
            canvas.create_line(x,yy,x+pw,yy,fill='#25344a')
            canvas.create_text(x-8,yy,text=f'{price:.2f}',anchor='e',fill=MUTED,font=(self.font_family,9))
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
        intervals=settings.angle_intervals
        start=len(row.ema9_points)-1-intervals;end=len(row.ema9_points)-1
        a=point(start,row.ema9_points[start]);b=point(end,row.ema9_points[end])
        canvas.create_line(*a,*b,fill=GOLD,width=3,tags=('measured_chord',))
        canvas.create_oval(b[0]-3,b[1]-3,b[0]+3,b[1]+3,fill=GOLD,outline=GOLD)
        for i in sorted(set([0,len(row.candles)//2,len(row.candles)-1])):
            xx,_=point(i,row.candles[i].close)
            canvas.create_text(xx,y+ph+17,text=row.candles[i].time.astimezone(IST).strftime('%d %b %H:%M'),fill=MUTED,font=(self.font_family,9))
        canvas.create_text(x+8,y+12,anchor='w',text='EMA9    EMA21    Gold: angle chord    Hollow: forming / observed OHLC',fill=MUTED,font=(self.font_family,9))

    def close(self):
        if self.closed:return
        self.closed=True;self.token.set('')
        if self.after_id:self.root.after_cancel(self.after_id);self.after_id=None
        try:self.scanner.close()
        finally:self.root.destroy()
