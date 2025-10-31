from tkinter import *
from tkinter import ttk
from models.toplevel import TopWindow
from models.datagrid import DataGrid


class WinCamerasRep (TopWindow):
    def __init__(self, master):
        super().__init__(master, title="Reporte de camaras",width=800,height=600, not_rezisable=False)

        btns = ttk.Frame(self, padding=10)
        btns.pack(fill="x", pady=10)

        btn_generate = ttk.Button(btns, text="Generar")
        btn_pdf = ttk.Button(btns, text="PDF")
        btn_word = ttk.Button(btns, text="WORD")
        btn_excel = ttk.Button(btns, text="EXCEL")
        btn_exit = ttk.Button(btns, text="Salir", command=self.destroy)
        
        btn_generate.pack(side="left", expand=True, padx=5)
        btn_pdf.pack(side="left", expand=True, padx=5)
        btn_word.pack(side="left", expand=True, padx=5)
        btn_excel.pack(side="left", expand=True, padx=5)
        btn_exit.pack(side="left", expand=True, padx=5)
        
        # Contenedor principal
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        dg_frame = ttk.Frame(main_frame)
        dg_frame.pack(fill="both", expand=True)

        self.datagrid = DataGrid(dg_frame, width=780, height=500)
        self.datagrid.add_columns(
            columns=["ID", "Cámara", "IP", "Ruta de Imagen"],
            widths=[15, 100, 150, 480]
        )
        
        
        
        
        
        
        self.mainloop()