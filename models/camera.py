class Camera:
    def __init__(self, name:str, ip:str, username:str, password:str, port:int = 554, id:int = None, stream_path:str = ""):
        self.id = id
        self.name = name
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.stream_path = stream_path

    def get_rtsp_url(self) -> str:
        """
        Construye la URL RTSP para la cámara.
        Nota: La ruta final puede variar según el fabricante (ej. /stream1, /cam/realmonitor, etc.).
        """
        # Si el nombre o IP es "demo", usar la webcam local
        if self.ip.lower() == "demo" or self.name.lower() == "cam demo":
            return 0

        if self.stream_path == "":
            path = "axis-media/media.amp?resolution=1280x720&videocodec=h264&fps=20"
        else:
            path = self.stream_path
        
        return f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/{path}"