class Event:
    def __init__(self, camera_id:int, timestamp:str, description:str, image_path:str = None, id:int = None):
        self.id = id
        self.camera_id = camera_id
        self.timestamp = timestamp
        self.description = description
        self.image_path = image_path

    def return_dict(self) -> dict:
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp,
            "description": self.description,
            "image_path": self.image_path
        }
    
    def return_image(self) -> str:
        return self.image_path