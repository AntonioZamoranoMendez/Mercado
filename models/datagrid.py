import tkinter as tk
from tkinter import ttk

class DataGrid:
    def __init__(self, master, width:int, height:int, bg="white", row_height:int=20):
        self.frame = tk.Frame(master, width=width, height=height, bg=bg)
        self.frame.pack_propagate(False)  # mantiene tamaño fijo
        self.frame.pack()

        rows = int((height-20)/row_height)

        self.tvw = ttk.Treeview(self.frame, selectmode="browse", height=rows, show="headings")
        self.vsb = ttk.Scrollbar(self.frame, orient="vertical", command=self.tvw.yview)
        self.hsb = ttk.Scrollbar(self.frame, orient="horizontal", command=self.tvw.xview)

        self.tvw.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        # Layout con grid, más limpio que place
        self.tvw.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")

        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

    def add_columns(self, columns: list, widths: list = None, anchors: list = None):
        self.tvw["columns"] = columns
        for i, col in enumerate(columns):
            w = widths[i] if widths and i < len(widths) else 100
            a = anchors[i] if anchors and i < len(anchors) else tk.CENTER
            self.tvw.column(col, width=w, anchor=a)
            self.tvw.heading(col, text=col)

    def insert_row(self, values: list, text: str = "", index="end", tags=""):
        return self.tvw.insert("", index, text=text, values=values, tags=tags)

    def clear(self):
        for row in self.tvw.get_children():
            self.tvw.delete(row)

    def select_row(self, index: int = -1, iid: str = None):
        rows = self.tvw.get_children()
        if not rows: return
        if iid:
            self.tvw.selection_set(iid)
            self.tvw.see(iid)
        else:
            if index == -1: index = len(rows)-1
            iid = rows[index]
            self.tvw.selection_set(iid)
            self.tvw.see(iid)
