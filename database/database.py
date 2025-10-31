import sqlite3
from models.camera import Camera
from models.event import Event
import os

class Database:
    def __init__(self, db_name="database.db"):
        """
        Inicializa la base de datos. Construye la ruta a la base de datos
        relativa a la ubicación de este archivo.
        """
        self.db_path = os.path.join(os.path.dirname(__file__), db_name)
        self._create_table()

    def _get_connection(self):
        """Crea y devuelve una conexión a la base de datos."""
        return sqlite3.connect(self.db_path)

    def _create_table(self):
        """Crea la tabla 'cameras' si no existe."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cameras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    ip TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    port INTEGER NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    description TEXT NOT NULL,
                    image_path TEXT,
                    FOREIGN KEY (camera_id) REFERENCES cameras (id)
                )
            ''')
            conn.commit()
        finally:
            if conn:
                conn.close()

    def get_all_cameras(self) -> list[Camera]:
        """Obtiene todas las cámaras de la base de datos y las devuelve como una lista de objetos Camera."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, ip, username, password, port FROM cameras ORDER BY name")
            rows = cursor.fetchall()
            return [Camera(id=row[0], name=row[1], ip=row[2], username=row[3], password=row[4], port=row[5]) for row in rows]
        finally:
            if conn:
                conn.close()

    def add_camera(self, camera: Camera) -> int:
        """Agrega una nueva cámara a la base de datos."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO cameras (name, ip, username, password, port) VALUES (?, ?, ?, ?, ?)",
                (camera.name, camera.ip, camera.username, camera.password, camera.port)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            if conn:
                conn.close()

    def update_camera(self, camera: Camera) -> bool:
        """Actualiza una cámara existente en la base de datos."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE cameras SET name=?, ip=?, username=?, password=?, port=? WHERE id=?",
                (camera.name, camera.ip, camera.username, camera.password, camera.port, camera.id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if conn:
                conn.close()

    def delete_camera(self, camera_id: int) -> bool:
        """Elimina una cámara de la base de datos por su ID."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if conn:
                conn.close()

    def get_events(self) -> list[Event]:
        """Obtiene todos los eventos de la base de datos y los devuelve como una lista de objetos Event."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, camera_id, timestamp, description
                FROM events
                ORDER BY timestamp DESC
            """)
            rows = cursor.fetchall()
            return [
                Event(
                    id=row[0],
                    camera_id=row[1],
                    timestamp=row[2],
                    description=row[3]
                )
                for row in rows
            ]
        finally:
            if conn:
                conn.close()



    def add_event(self, event: Event) -> int:
        """Agrega un nuevo evento a la base de datos."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (camera_id, timestamp, description, image_path) VALUES (?, ?, ?, ?)",
                (event.camera_id, event.timestamp, event.description, event.image_path)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            if conn:
                conn.close()

    def update_event(self, event: Event) -> bool:
        """Actualiza un evento existente en la base de datos."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE events SET camera_id=?, timestamp=?, description=?, image_path=? WHERE id=?",
                (event.camera_id, event.timestamp, event.description, event.image_path, event.id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if conn:
                conn.close()

    def delete_event(self, event_id: int) -> bool:
        """Elimina un evento de la base de datos por su ID."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM events WHERE id=?", (event_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if conn:
                conn.close()
