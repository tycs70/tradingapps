"""Stable table identities preserve the selected asset while rankings move."""
from tkinter import ttk
from .models import IST

BG='#0b1220';PANEL='#122035';TEXT='#e5edf8';MUTED='#98abc2';GREEN='#5de6b5';RED='#ff8895';TEAL='#35dbb4'

def angle(value):return '—' if value is None else f'{value:+.1f}°'
def stamp(value):return '—' if value is None else value.astimezone(IST).strftime('%H:%M:%S')
def price(row):
    if row.price is None:return '—'
    digits=getattr(row,'digits',None)
    if digits is None:digits=(3 if 'JPY' in row.key else 5) if row.group=='Forex' else 2
    return f'{row.price:,.{digits}f}'

class RankedSection(ttk.Frame):
    columns=('rank','asset','trend','state','cross','now','price','time')
    def __init__(self,parent,name,height,on_select):
        super().__init__(parent,padding=(14,10))
        head=ttk.Frame(self);head.pack(fill='x',pady=(0,8))
        ttk.Label(head,text=name,style='Section.TLabel').pack(side='left')
        self.count=ttk.Label(head,text='',style='Muted.TLabel');self.count.pack(side='right')
        frame=ttk.Frame(self);frame.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(frame,columns=self.columns,show='headings',height=height,selectmode='browse')
        labels=('#','Instrument','Trend','State','Cross EMA9 ∠','Now ∠','cTrader bid','Cross · IST')
        widths=(40,190,75,120,115,85,120,110)
        for key,label,width in zip(self.columns,labels,widths):
            self.tree.heading(key,text=label);self.tree.column(key,width=width,minwidth=width,stretch=key=='asset',anchor='w' if key in ('asset','state') else 'center')
        self.tree.tag_configure('LONG',foreground=GREEN,background='#102e2d')
        self.tree.tag_configure('SHORT',foreground=RED,background='#311f30')
        self.tree.tag_configure('INACTIVE',foreground=MUTED,background=PANEL)
        self.tree.pack(side='left',fill='both',expand=True)
        self.scrollbar=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview)
        self.scrollbar.pack(side='right',fill='y');self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.tree.bind('<<TreeviewSelect>>',lambda e:on_select(self.tree.selection()[0]) if self.tree.selection() else None)
        self._values={}
    def update_rows(self,rows):
        wanted={r.key for r in rows}
        for key in set(self.tree.get_children())-wanted:self.tree.delete(key);self._values.pop(key,None)
        for n,r in enumerate(rows):
            active=r.rank is not None
            values=(f'{r.rank:02d}' if active else '—',r.name,r.side if active else '—',r.status,
                    angle(r.captured_angle),angle(r.current_angle),price(r),stamp(r.signal_time))
            tag=r.side if active else 'INACTIVE'
            if self._values.get(r.key)!=(values,tag):
                if self.tree.exists(r.key):self.tree.item(r.key,values=values,tags=(tag,))
                else:self.tree.insert('','end',iid=r.key,values=values,tags=(tag,))
                self._values[r.key]=(values,tag)
            self.tree.move(r.key,'',n)
        self.count.configure(text=f'{sum(r.rank is not None for r in rows)} ranked / {len(rows)} instruments')
