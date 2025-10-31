from tkinter import *
from tkinter import ttk
from models.toplevel import TopWindow
from models.datagrid import DataGrid
from database.database import Database

class WinEvents(TopWindow):
    def __init__(self, master):
        super().__init__(master, title="Mercado - Eventos", width=800, height=600, not_rezisable=False)
        self.db = Database()

        # Contenedor principal
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

                # --- Barra de búsqueda ---
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 10))

        self.search_var = StringVar(self)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side="left", expand=True, fill="x", padx=5)

        # Placeholder
        placeholder = "Buscar por cámara o descripción..."
        search_entry.insert(0, placeholder)
        search_entry.config(foreground="gray")

        def on_focus_in(event):
            if search_entry.get() == placeholder:
                search_entry.delete(0, "end")
                search_entry.config(foreground="black")

        def on_focus_out(event):
            if search_entry.get() == "":
                search_entry.insert(0, placeholder)
                search_entry.config(foreground="gray")

        search_entry.bind("<FocusIn>", on_focus_in)
        search_entry.bind("<FocusOut>", on_focus_out)

        # Botón de búsqueda
        btn_search = ttk.Button(search_frame, text="Buscar", command=self.search_events)
        btn_search.pack(side="left", padx=5)


        # --- DataGrid ---
        dg_frame = ttk.Frame(main_frame)
        dg_frame.pack(fill="both", expand=True)

        self.datagrid = DataGrid(dg_frame, width=780, height=500)
        self.datagrid.add_columns(
            columns=["ID", "Cámara", "Fecha y Hora", "Descripción"],
            widths=[15, 100, 150, 480]
        )
        self.load_events()

        # --- Botón de salir ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(10, 0))

    def load_events(self):
        self.datagrid.clear()
        try:
            events = self.db.get_events()
            print(f"Eventos obtenidos: {len(events)}")
            for event in events:
                print(f"Inserting: {event.id}, {event.camera_id}, {event.timestamp}, {event.description}")
                self.datagrid.insert_row(
                    values=[event.id, event.camera_id, event.timestamp, event.description]
                )
        except Exception as e:
            print(f"Error al cargar eventos: {e}")


    def search_events(self):
        keyword = self.search_var.get().strip().lower()
        placeholder = "buscar por cámara o descripción..."

        self.datagrid.clear()
        events = self.db.get_events()

        # Si está vacío o tiene el placeholder, mostrar todos los eventos
        if not keyword or keyword == placeholder:
            filtered = events
        else:
            filtered = [
                e for e in events
                if keyword in str(e.camera_id).lower() or keyword in str(e.description).lower()
            ]

        for event in filtered:
            self.datagrid.insert_row(
                values=[event.id, event.camera_id, event.timestamp, event.description]
            )


if __name__ == "__main__":
    root = Tk()
    app = WinEvents(root)
    root.mainloop()
