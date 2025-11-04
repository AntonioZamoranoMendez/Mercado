from tkinter import *
from tkinter import ttk
from models.toplevel import TopWindow 

class WinHelp(TopWindow):
    def __init__(self, master):
        super().__init__(master, title="Ayuda", width=650, height=450, not_rezisable=False)

        # Frame para contenido principal
        content_frame = ttk.Frame(self, padding=15)
        content_frame.pack(fill=BOTH, expand=True, side=TOP)

        # Hacer que el frame no se reduzca automáticamente al contenido
        content_frame.pack_propagate(False)

        # Título centrado y más grande
        title_label = ttk.Label(
            content_frame, 
            text="Manual de uso", 
            font=("Helvetica", 18, "bold"), 
            justify=CENTER
        )
        title_label.pack(pady=(0, 15))

        # Texto explicativo centrado y un poco más grande
        help_text = (
            "\nBienvenido al Sistema de Cámaras.\n\n"
            "En esta ventana puedes:\n\n"
            "   1. Ver la cámara seleccionada en el panel izquierdo.\n\n"
            "   2. Elegir qué cámara ver desde el panel derecho.\n\n"
            "   3. Revisar los eventos detectados debajo de la lista de cámaras.\n\n"
            "   4. Visualizar imágenes capturadas al hacer clic en un evento.\n\n"
            "   5. Agregar, editar o eliminar cámaras usando los botones inferiores.\n\n"
            "   6. Checar reportes desde el menú superior llamado de la misma manera.\n\n"
            "Explora y revisa las detecciones en tiempo real de tus cámaras."
        )

        help_label = ttk.Label(
            content_frame, 
            text=help_text, 
            wraplength=560,       # Ajusta al ancho de la ventana
            justify=LEFT,         # Justificación izquierda para listas
            font=("Helvetica", 12)
        )
        help_label.pack(pady=(0, 20))


        # Mantener la ventana activa
        self.mainloop()

# Para probar directamente
if __name__ == "__main__":
    root = Tk()
    root.withdraw()  # Oculta la ventana principal
    WinHelp(root)
