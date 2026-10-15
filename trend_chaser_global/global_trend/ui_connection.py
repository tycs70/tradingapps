"""Read-only cTrader authorization and explicit instrument mapping controls."""
import tkinter as tk
from tkinter import ttk,messagebox
import webbrowser
from dataclasses import replace
from .connection import ConnectionController,MappingStore
from .catalog import CatalogEntry,GROUPS,default_catalog


class ConnectionPanel(ttk.Frame):
    def __init__(self,parent,engine,credentials,mappings=None,demo=False):
        super().__init__(parent,padding=20);self.demo=demo;self.engine=engine;self.mappings=mappings
        self.controller=None if demo else ConnectionController(engine,credentials,mappings)
        self.client_id=tk.StringVar();self.secret=tk.StringVar();self.redirect=tk.StringVar(value='http://localhost/')
        self.code=tk.StringVar();self.account=tk.StringVar();self.remember=tk.BooleanVar(value=False)
        self.message=tk.StringVar(value='Offline sample: authorization is disabled.' if demo else '1. Register an application at openapi.ctrader.com. See Help for the full guide.')
        self.columnconfigure(1,weight=1)
        ttk.Label(self,text='Connect cTrader Demo',style='Section.TLabel').grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,12))
        entries=[]
        for row,label,var,mask in ((1,'Client ID',self.client_id,False),(2,'Client secret',self.secret,True),
                                   (3,'Registered redirect URI',self.redirect,False),(5,'Authorization code / redirect URL',self.code,True)):
            ttk.Label(self,text=label).grid(row=row,column=0,sticky='w',padx=(0,18),pady=6)
            entry=ttk.Entry(self,textvariable=var,show='•' if mask else '',width=58)
            entry.grid(row=row,column=1,columnspan=2,sticky='ew');entries.append(entry)
            if row==2:self.secret_entry=entry
            if row==5:self.code_entry=entry
        self.buttons=[]
        def button(text,command,row,col=1):
            b=ttk.Button(self,text=text,command=lambda:self.safe(command));b.grid(row=row,column=col,sticky='w',pady=6)
            self.buttons.append(b);return b
        button('Open read-only authorization',self.open_authorization,4)
        button('Exchange code',self.exchange,6)
        button('Load demo accounts',self.load_accounts,6,2)
        ttk.Label(self,text='Authorized demo account').grid(row=7,column=0,sticky='w')
        self.account_combo=ttk.Combobox(self,textvariable=self.account,state='readonly',width=55)
        self.account_combo.grid(row=7,column=1,columnspan=2,sticky='ew',pady=8)
        self.connect_button=button('Connect data',self.connect_data,8)
        button('Disconnect',self.disconnect,8,2)
        self.remember_button=ttk.Checkbutton(self,text='Remember on this Windows user (DPAPI)',variable=self.remember)
        self.remember_button.grid(row=9,column=1,sticky='w',pady=5)
        if not credentials.available or demo:self.remember_button.state(['disabled'])
        button('Forget credentials',self.forget,9,2)
        ttk.Label(self,textvariable=self.message,style='Muted.TLabel',wraplength=900).grid(row=10,column=0,columnspan=3,sticky='ew',pady=10)
        ttk.Label(self,text='Quotes come from cTrader demo. Place any trades manually on Olymp Trade.',style='Muted.TLabel').grid(row=11,column=0,columnspan=3,sticky='w')
        button('Instrument mappings / verify Olymp match…',self.edit_mappings,12)
        if demo:
            for b in self.buttons:b.state(['disabled'])
            for entry in entries:entry.state(['disabled'])
        else:
            self.controller.restore()
            if self.controller.config:
                self.client_id.set(self.controller.config[0]);self.secret.set(self.controller.config[1]);self.redirect.set(self.controller.config[2]);self.remember.set(self.controller.remember)
                self.message.set(self.controller.message)
        self._account_values=()
    def safe(self,action):
        try:action()
        except (ValueError,RuntimeError):self.message.set('Check the current step and application details. Wait for any pending request, then retry.')
        except Exception:self.message.set('This step could not complete. Check the connection guide and retry.')
    def _configure(self):
        self.controller.configure(self.client_id.get(),self.secret.get(),self.redirect.get())
        self.controller.remember=self.remember.get()
    def open_authorization(self):
        self._configure();webbrowser.open(self.controller.oauth.authorization_url())
        self.message.set('Approve read-only access in the browser. Paste the code or complete redirect URL below.')
    def exchange(self):self._configure();self.controller.exchange(self.code.get());self.code.set('')
    def load_accounts(self):self._configure();self.controller.load_accounts()
    def connect_data(self):
        self._configure()
        i=self.account_combo.current()
        if i<0:raise ValueError('Select a demo account.')
        self.controller.connect(self.controller.accounts[i]['account_id'])
    def disconnect(self):self.controller.disconnect()
    def forget(self):
        self.controller.forget();self.secret.set('');self.code.set('');self.account.set('')
    def poll(self):
        if not self.controller:return
        self.controller.poll();self.message.set(self.controller.message)
        values=tuple(f"{a['broker']} · Demo · {a['login']}" for a in self.controller.accounts)
        if values!=self._account_values:
            self.account_combo.configure(values=values);self._account_values=values
            if values:self.account_combo.current(0)
        for b in self.buttons:b.state(['disabled'] if self.controller.busy else ['!disabled'])
    def edit_mappings(self):
        c=self.controller
        if not c.account or not self.mappings:
            self.message.set('Connect the demo account once before editing its instrument mappings.');return
        window=tk.Toplevel(self);window.title('Instrument mappings · current demo account');window.geometry('940x570')
        rows=list(self.mappings.load(c.account));selected=[None]
        ttk.Label(window,text='Verify the same underlying, contract and availability in Olymp Trade before confirming.',padding=12).pack(anchor='w')
        tree=ttk.Treeview(window,columns=('group','olymp','ctrader','verified'),show='headings',height=10)
        for col in ('group','olymp','ctrader','verified'):tree.heading(col,text=col.title());tree.column(col,width=180)
        tree.pack(fill='both',expand=True,padx=12)
        form=ttk.Frame(window,padding=12);form.pack(fill='x');variables={}
        for n,(key,label) in enumerate((('key','Unique key'),('group','Section'),('olymp_name','Olymp name'),('ctrader_name','Exact cTrader name'))):
            variables[key]=tk.StringVar()
            ttk.Label(form,text=label).grid(row=0,column=n,sticky='w')
            entry=ttk.Combobox(form,textvariable=variables[key],values=GROUPS,state='readonly',width=14) if key=='group' else ttk.Entry(form,textvariable=variables[key],width=22)
            entry.grid(row=1,column=n,padx=(0,8))
        verified=tk.BooleanVar();ttk.Checkbutton(form,text='I verified this same instrument on Olymp Trade',variable=verified).grid(row=2,column=0,columnspan=4,sticky='w',pady=10)
        info=tk.StringVar(value='Editing a name revokes confirmation. Select the saved row and confirm again after checking.')
        ttk.Label(window,textvariable=info,padding=10,wraplength=880).pack(fill='x')
        def render():
            tree.delete(*tree.get_children())
            for n,e in enumerate(rows):tree.insert('','end',iid=str(n),values=(e.group,e.olymp_name,e.ctrader_name,'Verified' if e.verified else 'Pending'))
        def choose(event=None):
            if not tree.selection():return
            n=int(tree.selection()[0]);selected[0]=n;e=rows[n]
            for key,var in variables.items():var.set(getattr(e,key))
            verified.set(e.verified)
        tree.bind('<<TreeviewSelect>>',choose)
        def update():
            try:
                e=CatalogEntry(**{k:v.get().strip() for k,v in variables.items()},verified=verified.get())
                old=rows[selected[0]] if selected[0] is not None else None
                if old and (old.key!=e.key or old.group!=e.group or old.olymp_name!=e.olymp_name or old.ctrader_name!=e.ctrader_name):e=replace(e,verified=False)
                candidate=list(rows)
                if old:candidate[selected[0]]=e
                else:candidate.append(e)
                MappingStore.validate(candidate);rows[:]=candidate;render();selected[0]=None
                info.set('Row updated. Save and reconnect to apply. Renamed rows need a second confirmation.')
            except (ValueError,TypeError):info.set('Use a unique uppercase key, valid section and exact instrument names.')
        def new():
            selected[0]=None
            for var in variables.values():var.set('')
            variables['group'].set('Shares');verified.set(False)
        def remove():
            if selected[0] is not None:rows.pop(selected[0]);selected[0]=None;render()
        def save():
            try:
                self.mappings.save(c.account,rows);c.disconnect();self.message.set('Mappings saved. Connect data to reload and revalidate history.');window.destroy()
            except (OSError,ValueError):info.set('Mappings could not be saved. Check the rows and data directory.')
        bar=ttk.Frame(window,padding=12);bar.pack(fill='x')
        for text,action in (('New row',new),('Update row',update),('Remove row',remove),('Save and disconnect',save)):
            ttk.Button(bar,text=text,command=action).pack(side='left',padx=5)
        render()
    def close(self):
        if self.controller:self.controller.close()
