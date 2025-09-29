import carla
import socket
import struct
import numpy as np
from PIL import Image
import io
import time

# ===== Konfiguration =====
CARLA_HOST = '127.0.0.1'
CARLA_PORT = 2000

LISTEN_HOST = '0.0.0.0'
LISTEN_PORT = 5001

IMG_WIDTH = 1280
IMG_HEIGHT = 720
JPEG_QUALITY = 80
FOV = 90.0

def start_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(1)
    print(f"[TCP] Warte auf Unity… ({LISTEN_HOST}:{LISTEN_PORT})")
    conn, addr = srv.accept()
    print(f"[TCP] Verbunden mit {addr}")
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return srv, conn

def send_jpeg(conn, jpeg_bytes):
    header = struct.pack('!I', len(jpeg_bytes))
    conn.sendall(header)
    conn.sendall(jpeg_bytes)

def pick_vehicle_bp(bp):
    # versuche spezifische Modelle, sonst irgendein Fahrzeug
    preferred = [
        'vehicle.tesla.model3',
        'vehicle.nissan.patrol',
        'vehicle.lincoln.mkz_2017',
    ]
    for name in preferred:
        try:
            return bp.find(name)
        except:
            pass
    candidates = bp.filter('vehicle.*')
    if not candidates:
        raise RuntimeError("Keine vehicle Blueprints gefunden.")
    return candidates[0]

def main():
    # TCP-Server starten (vor Unity Play!)
    srv, conn = start_server()

    client = carla.Client(CARLA_HOST, CARLA_PORT)
    client.set_timeout(10.0)
    world = client.get_world()
    bp = world.get_blueprint_library()

    # Kamera-Blueprint
    cam_bp = bp.find('sensor.camera.rgb')
    cam_bp.set_attribute('image_size_x', str(IMG_WIDTH))
    cam_bp.set_attribute('image_size_y', str(IMG_HEIGHT))
    cam_bp.set_attribute('fov', str(FOV))

    # Fahrzeug besorgen/erstellen
    vehicles = world.get_actors().filter('vehicle.*')
    if vehicles:
        vehicle = vehicles[0]
        print("[CARLA] Nutze vorhandenes Fahrzeug:", vehicle.type_id)
    else:
        vehicle_bp = pick_vehicle_bp(bp)
        spawn_points = world.get_map().get_spawn_points()
        if not spawn_points:
            raise RuntimeError("Keine Spawnpunkte im aktuellen Level.")
        vehicle = world.try_spawn_actor(vehicle_bp, spawn_points[0])
        if vehicle is None:
            raise RuntimeError("Konnte Fahrzeug nicht spawnen.")
        print("[CARLA] Neues Fahrzeug gespawnt:", vehicle.type_id)

    # Kamera montieren
    cam_transform = carla.Transform(carla.Location(x=1.5, z=1.4))
    camera = world.spawn_actor(cam_bp, cam_transform, attach_to=vehicle)

    def image_callback(image):
        arr = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(image.height, image.width, 4)
        rgb = arr[:, :, :3][:, :, ::-1]  # BGRA -> RGB
        pil_img = Image.fromarray(rgb)
        with io.BytesIO() as buf:
            pil_img.save(buf, format='JPEG', quality=JPEG_QUALITY)
            jpeg = buf.getvalue()
        try:
            send_jpeg(conn, jpeg)
        except Exception as e:
            print("[TCP] Sendefehler:", e)

    camera.listen(image_callback)
    print("Streaming… Strg+C zum Beenden.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()
        camera.destroy()
        conn.close()
        srv.close()
        print("Beendet.")

if __name__ == '__main__':
    main()

