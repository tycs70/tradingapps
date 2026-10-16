"""Tk dashboard: immutable snapshots, stable rankings and optional reference chart."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from . import APP_NAME,VERSION
from .models import IST
from .models import Settings
from .connection import MappingStore
from .ui_connection import ConnectionPanel
from .ui_tables import RankedSection,BG,PANEL,TEXT,MUTED,GREEN,RED,TEAL,angle,price,stamp


class App:
    def __init__(self,root,engine,settings_store,credentials,demo=False):
        self.root=root;self.engine=engine;self.settings_store=settings_store;self.demo=demo
        self.closed=False;self._after=None;self.selected=None;self.rows={};self._chart_snapshot=None
        root.title(f'{APP_NAME} {VERSION}'+(' · OFFLINE SAMPLE' if demo else ''))
        root.geometry('1280x900');root.minsize(1120,720);root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.report_callback_exception=lambda *args:self.status.set('The display could not update. Disconnect and reopen the app.')
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',background=BG,foreground=TEXT,font=('Segoe UI',10))
        style.configure('TFrame',background=BG);style.configure('TLabel',background=BG,foreground=TEXT)
        style.configure('Title.TLabel',font=('Segoe UI',25,'bold'));style.configure('Section.TLabel',font=('Segoe UI',14,'bold'))
        style.configure('Muted.TLabel',foreground=MUTED);style.configure('Badge.TLabel',foreground=TEAL,font=('Segoe UI',11,'bold'))
        style.configure('TButton',background='#223953',foreground=TEXT,padding=(12,7),borderwidth=0)
        style.map('TButton',background=[('active','#305571')],foreground=[('disabled','#718399')])
        style.configure('TEntry',fieldbackground=PANEL,foreground=TEXT,insertcolor=TEXT,padding=5)
        style.configure('TCombobox',fieldbackground=PANEL,foreground=TEXT,arrowcolor=TEAL)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=31,borderwidth=0,font=('Segoe UI',10))
        style.configure('Treeview.Heading',background='#1e3048',foreground=MUTED,font=('Segoe UI',9,'bold'),padding=(5,10))
        style.map('Treeview',background=[('selected','#315674')],foreground=[('selected','#ffffff')])
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',background='#192940',padding=(18,9),foreground=MUTED)
        style.map('TNotebook.Tab',background=[('selected','#28445e')],foreground=[('selected',TEAL)])
        head=ttk.Frame(root,padding=(22,18));head.pack(fill='x')
        self.icon=None
        icon=Path(__file__).resolve().parent.parent/'assets/icon.png'
        if icon.exists():
            try:
                original=tk.PhotoImage(file=str(icon));root.iconphoto(True,original)
                self.icon=original.subsample(max(1,original.width()//56));ttk.Label(head,image=self.icon).pack(side='left',padx=(0,15))
            except tk.TclError:pass
        brand=ttk.Frame(head);brand.pack(side='left')
        ttk.Label(brand,text='Trend Chaser Global',style='Title.TLabel').pack(anchor='w')
        ttk.Label(brand,text='5 MIN  /  EMA9 × EMA21  /  THREE MARKETS',style='Muted.TLabel').pack(anchor='w',pady=(3,0))
        self.source=tk.StringVar();ttk.Label(head,textvariable=self.source,style='Badge.TLabel').pack(side='right')
        self.notebook=ttk.Notebook(root);self.notebook.pack(fill='both',expand=True,padx=18,pady=(0,8))
        self.dashboard=ttk.Frame(self.notebook);self.notebook.add(self.dashboard,text='Dashboard')
        mappings=None if demo else MappingStore(settings_store.path.parent/'mappings.json')
        self.connection=ConnectionPanel(self.notebook,engine,credentials,mappings,demo)
        self.notebook.add(self.connection,text='Connect cTrader')
        self.events_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(self.events_tab,text='Events')
        self.chart_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(self.chart_tab,text='Reference chart')
        self.help_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(self.help_tab,text='Help & rules')
        self.diagnostics_tab=ttk.Frame(self.notebook,padding=14);self.notebook.add(self.diagnostics_tab,text='Diagnostics & settings')
        self.diagnostics_text=tk.StringVar()
        ttk.Label(self.diagnostics_tab,textvariable=self.diagnostics_text,wraplength=1000,justify='left').pack(anchor='w',pady=(0,20))
        prefs=Settings() if demo else settings_store.load()
        self.day_boundary=tk.StringVar(value=prefs.day_boundary);self.day_zone=tk.StringVar(value=prefs.day_zone)
        self.proximity=tk.StringVar(value=str(prefs.proximity_pct));self.chart_bars=tk.StringVar(value=str(prefs.chart_bars));self.angle_intervals=tk.StringVar(value=str(prefs.angle_intervals))
        for label,var in (('Daily reset time (HH:MM)',self.day_boundary),('Daily reset IANA time zone',self.day_zone),('Proximity %',self.proximity),('Reference chart candles',self.chart_bars),('EMA9 angle intervals',self.angle_intervals)):
            row=ttk.Frame(self.diagnostics_tab);row.pack(fill='x',pady=5)
            ttk.Label(row,text=label,width=32).pack(side='left');ttk.Entry(row,textvariable=var,width=30).pack(side='left')
        apply=ttk.Button(self.diagnostics_tab,text='Save settings and restart scanner',command=self.save_preferences);apply.pack(anchor='w',pady=12)
        if demo:apply.state(['disabled'])
        self.preferences_message=tk.StringVar(value='Freshness: 15 seconds. Saving settings disconnects and clears active membership; reconnect to observe new crosses.')
        ttk.Label(self.diagnostics_tab,textvariable=self.preferences_message,wraplength=1000,style='Muted.TLabel').pack(anchor='w')
        self.metrics=tk.StringVar();ttk.Label(self.dashboard,textvariable=self.metrics,style='Badge.TLabel',padding=(14,12)).pack(fill='x')
        ttk.Label(self.dashboard,text='Rank = frozen EMA9 crossover strength  ·  LONG / SHORT compete in each section  ·  Times: IST',style='Muted.TLabel',padding=(14,0,14,6)).pack(fill='x')
        self.sections={}
        self.index_frame=RankedSection(self.dashboard,'Indices · pinned',3,self.select_asset)
        self.index_frame.pack(fill='x');self.sections['Indices']=self.index_frame
        lower=ttk.Frame(self.dashboard);lower.pack(fill='both',expand=True)
        self.lower_canvas=tk.Canvas(lower,bg=BG,highlightthickness=0)
        outer_scroll=ttk.Scrollbar(lower,orient='vertical',command=self.lower_canvas.yview)
        self.lower_canvas.configure(yscrollcommand=outer_scroll.set);outer_scroll.pack(side='right',fill='y');self.lower_canvas.pack(side='left',fill='both',expand=True)
        content=ttk.Frame(self.lower_canvas);self._canvas_window=self.lower_canvas.create_window(0,0,anchor='nw',window=content)
        content.bind('<Configure>',lambda e:self.lower_canvas.configure(scrollregion=self.lower_canvas.bbox('all')))
        self.lower_canvas.bind('<Configure>',lambda e:self.lower_canvas.itemconfigure(self._canvas_window,width=e.width))
        self.lower_canvas.bind('<MouseWheel>',lambda e:self.lower_canvas.yview_scroll(-int(e.delta/120),'units'))
        for group,height in (('Forex',6),('Shares',5)):
            section=RankedSection(content,group,height,self.select_asset);section.pack(fill='x',pady=(5,10));self.sections[group]=section
        foot=ttk.Frame(root,padding=(22,8));foot.pack(fill='x')
        self.detail=tk.StringVar(value='Select an instrument for signal and quote details.')
        ttk.Label(foot,textvariable=self.detail,style='Muted.TLabel',wraplength=1000).pack(side='left',fill='x',expand=True)
        ttk.Button(foot,text='View reference chart',command=self.show_chart).pack(side='right')
        self.status=tk.StringVar();ttk.Label(root,textvariable=self.status,style='Muted.TLabel',padding=(22,0,22,10)).pack(fill='x')
        self.events=ttk.Treeview(self.events_tab,columns=('time','asset','action','reason'),show='headings',height=15)
        for col,width in (('time',110),('asset',150),('action',180),('reason',650)):
            self.events.heading(col,text=col.title());self.events.column(col,width=width,stretch=col=='reason')
        scroll=ttk.Scrollbar(self.events_tab,command=self.events.yview);self.events.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.events.pack(fill='both',expand=True)
        self.chart_label=tk.StringVar(value='Select an instrument on the dashboard.')
        ttk.Label(self.chart_tab,textvariable=self.chart_label,style='Section.TLabel').pack(anchor='w')
        ttk.Label(self.chart_tab,text='EMA9: teal   ·   EMA21: gold   ·   Reference plot keeps a 2:1 aspect ratio; it is not an Olymp Trade chart.',style='Muted.TLabel').pack(anchor='w',pady=10)
        self.chart=tk.Canvas(self.chart_tab,bg=PANEL,highlightthickness=0);self.chart.pack(fill='both',expand=True)
        self.chart.bind('<Configure>',lambda e:self.draw_chart())
        text=tk.Text(self.help_tab,wrap='word',bg=PANEL,fg=TEXT,insertbackground=TEXT,padx=20,pady=20,font=('Segoe UI',11),relief='flat')
        scrollbar=ttk.Scrollbar(self.help_tab,command=text.yview);text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        guide=Path(__file__).resolve().parent.parent/'docs/CONNECT_CTRADER.md'
        text.insert('1.0',guide.read_text(encoding='utf-8') if guide.exists() else 'See the included connection guide.');text.configure(state='disabled')
        self.refresh()
    def refresh(self):
        if self.closed:return
        if self._after:
            self.root.after_cancel(self._after);self._after=None
        self.connection.poll();state=self.engine.snapshot()
        self.source.set(state.source)
        self.metrics.set(f"{state.counts.get('ranked',0):02d} RANKED     /     {state.counts.get('fresh',0):02d} FRESH     /     {state.counts.get('history_ready',0):02d} HISTORY READY     /     {state.counts.get('mapped',0):02d} MAPPED")
        self.rows={r.key:r for rows in state.groups.values() for r in rows}
        for group,section in self.sections.items():section.update_rows(state.groups[group])
        self.status.set(state.status+'  ·  cTrader prices may differ from Olymp Trade. Manual trading only.')
        counts='  |  '.join(f'{k}: {v}' for k,v in state.counts.items())
        self.diagnostics_text.set(state.status+'\n\n'+counts+'\n\n'+'\n'.join(str(d) for d in state.diagnostics[-12:]))
        present=set(self.events.get_children())
        for event in state.events:
            key=str(event.sequence)
            if key not in present:self.events.insert('','end',iid=key,values=(stamp(event.time),event.symbol,event.action or event.state,event.reason))
        keep={str(e.sequence) for e in state.events}
        for key in present-keep:self.events.delete(key)
        if self.selected in self.rows:self.select_asset(self.selected)
        self._after=self.root.after(250,self.refresh)
    def select_asset(self,key):
        self.selected=key;r=self.rows.get(key)
        if not r:return
        ema=lambda v:'—' if v is None else f'{v:.5f}'
        distance='—' if r.distance_pct is None else f'{r.distance_pct:+.3f}%'
        self.detail.set(f'{r.name} · {r.status} · Bid {price(r)} · Quote {stamp(r.quote_time)} IST · Cross {angle(r.captured_angle)} · Now {angle(r.current_angle)}\nEMA9 {ema(r.ema9)} / EMA21 {ema(r.ema21)} · Distance {distance} · {r.reason}')
        if self._chart_snapshot is not r.snapshot:self._chart_snapshot=r.snapshot;self.draw_chart()
    def show_chart(self):
        self.notebook.select(self.chart_tab);self.root.after_idle(self.draw_chart)
    def draw_chart(self):
        if self.closed:return
        c=self.chart;c.delete('all');r=self.rows.get(self.selected)
        if not r or not r.snapshot:
            c.create_text(30,40,anchor='w',text='A fresh, validated history is required for the reference chart.',fill=MUTED);return
        s=r.snapshot;self.chart_label.set(f'{r.name} · 5m · cTrader bid {price(r)} · EMA9 now {angle(r.current_angle)}')
        width=min(max(200,c.winfo_width()-90),max(100,c.winfo_height()-60)*2);height=width/2
        left,top=25,20
        def point(n,p):
            x,y=s.scale.point(n,p,width,height);return left+x,top+y
        for level in range(5):
            y=top+height*level/4;c.create_line(left,y,left+width,y,fill='#263851')
            value=s.scale.maximum-(s.scale.maximum-s.scale.minimum)*level/4
            c.create_text(left+width+8,y,text=f'{value:.5f}' if r.group=='Forex' else f'{value:,.2f}',anchor='w',fill=MUTED,font=('Segoe UI',8))
        body=max(2,min(8,width/len(s.candles)*.55))
        for n,bar in enumerate(s.candles):
            x,y=point(n,bar.close);_,o=point(n,bar.open);_,h=point(n,bar.high);_,l=point(n,bar.low);color=GREEN if bar.close>=bar.open else RED
            c.create_line(x,h,x,l,fill=color);c.create_rectangle(x-body/2,min(o,y),x+body/2,max(o,y)+1,fill=color,outline=color)
        for values,color,tag in ((s.ema9_points,TEAL,'ema9'),(s.ema21_points,'#f4c46a','ema21')):
            coordinates=[v for n,p in enumerate(values) for v in point(n,p)]
            c.create_line(*coordinates,fill=color,width=2,tags=tag)
        c.create_text(left,top+height+20,text=s.candles[0].time.astimezone(IST).strftime('%d %b %H:%M IST'),anchor='w',fill=MUTED)
        c.create_text(left+width,top+height+20,text=s.quote_time.astimezone(IST).strftime('%d %b %H:%M IST'),anchor='e',fill=MUTED)
    def close(self):
        if self.closed:return
        self.closed=True
        if self._after:
            try:self.root.after_cancel(self._after)
            except tk.TclError:pass
        self.connection.close();self.engine.close()
        try:self.root.destroy()
        except tk.TclError:pass

    def save_preferences(self):
        if self.demo:return
        try:
            settings=Settings(proximity_pct=float(self.proximity.get()),chart_bars=int(self.chart_bars.get()),angle_intervals=int(self.angle_intervals.get()),
                              remember_token=self.connection.remember.get(),day_boundary=self.day_boundary.get(),day_zone=self.day_zone.get())
            self.connection.disconnect();self.settings_store.save(settings)
            self.engine.reconfigure(settings)
            self.preferences_message.set('Settings saved. Connect data again; new observed crosses will use the new geometry and day boundary.')
        except (ValueError,TypeError):self.preferences_message.set('Check the values: chart candles 20–120, angle intervals 1–5, proximity 0.001–0.5%, valid daily time and IANA zone.')
        except OSError:self.preferences_message.set('Settings could not be saved. Check the app data directory.')
