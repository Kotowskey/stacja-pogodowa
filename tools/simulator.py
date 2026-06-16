"""Symulator węzłów ESP32 - publikuje fałszywe pomiary do brokera MQTT.

Pozwala uruchomić cały system bez fizycznych ESP32. Każdy węzeł publikuje
co `--interval` sekund pomiar na topic `weather/<node_id>/data`.

Przykład:
    python tools/simulator.py --host localhost --port 1883 --interval 2
    python tools/simulator.py --nodes esp32-01,esp32-02,esp32-03
"""

from __future__ import annotations

import argparse
import json
import math
import random
import signal
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import paho.mqtt.client as mqtt


@dataclass
class NodeProfile:
    """Profil termodynamiczny pojedynczego "węzła" - każdy ma trochę inne warunki."""

    node_id: str
    base_temp: float
    base_distance: float
    base_lux: float
    phase: float  # przesunięcie sinusoidy temperatury


def make_default_nodes(ids: List[str]) -> List[NodeProfile]:
    profiles: List[NodeProfile] = []
    rng = random.Random(42)
    for i, node_id in enumerate(ids):
        profiles.append(
            NodeProfile(
                node_id=node_id,
                base_temp=18.0 + rng.uniform(-2.0, 6.0),
                base_distance=100.0 + rng.uniform(-40.0, 80.0),
                base_lux=400.0 + rng.uniform(-150.0, 300.0),
                phase=i * math.pi / 4,
            )
        )
    return profiles


def sample(profile: NodeProfile, t: float) -> dict:
    """Generuje pomiar dla zadanego czasu `t` (sekundy od startu).

    Temperatura ma składową dobową (sinusoida), do której doklejamy szum.
    """
    daily = math.sin(2 * math.pi * (t / 600.0) + profile.phase)
    temperature = profile.base_temp + 3.0 * daily + random.uniform(-0.2, 0.2)
    distance = profile.base_distance + 20.0 * math.sin(t / 700.0 + profile.phase) + random.uniform(-1.0, 1.0)
    distance = max(2.0, distance)
    lux = profile.base_lux + 250.0 * daily + random.uniform(-15.0, 15.0)
    lux = max(0.0, lux)

    return {
        "node_id": profile.node_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "temperature": round(temperature, 2),
        "distance": round(distance, 2),
        "lux": round(lux, 1),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Symulator węzłów ESP32 dla monitorowania wnętrza czołgu.")
    p.add_argument("--host", default="localhost", help="Adres brokera MQTT (domyślnie localhost)")
    p.add_argument("--port", type=int, default=8883, help="Port brokera MQTT (8883=TLS, 1883=plain)")
    p.add_argument("--tls", action="store_true", help="Połączenie MQTT over TLS (port 8883)")
    p.add_argument(
        "--cafile",
        default="mosquitto/certs/ca.crt",
        help="Certyfikat CA brokera (wymagany przy --tls)",
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        help="Wyłącz weryfikację certyfikatu (tylko dev)",
    )
    p.add_argument(
        "--nodes",
        default="esp32-01,esp32-02,esp32-03",
        help="Lista identyfikatorów węzłów rozdzielona przecinkami",
    )
    p.add_argument("--interval", type=float, default=2.0, help="Co ile sekund publikować pomiar")
    p.add_argument("--qos", type=int, default=1, choices=[0, 1, 2], help="QoS publikacji")
    p.add_argument("--username", default="esp32_user", help="Login MQTT")
    p.add_argument("--password", default="iot-dev-pass", help="Hasło MQTT")
    return p.parse_args()


def _resolve_cafile(path: str) -> Optional[str]:
    p = Path(path)
    if p.is_absolute():
        return str(p) if p.exists() else None
    repo_root = Path(__file__).resolve().parent.parent
    resolved = repo_root / p
    return str(resolved) if resolved.exists() else None


def main() -> None:
    args = parse_args()
    node_ids = [n.strip() for n in args.nodes.split(",") if n.strip()]
    if not node_ids:
        print("Brak węzłów do symulacji - przerwano.", file=sys.stderr)
        sys.exit(1)

    profiles = make_default_nodes(node_ids)

    use_tls = args.tls or args.port == 8883
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"simulator-{int(time.time())}")
    if args.username:
        client.username_pw_set(args.username, args.password or None)

    if use_tls:
        cafile = _resolve_cafile(args.cafile)
        if not cafile and not args.insecure:
            print(
                f"Brak pliku CA: {args.cafile}. Uruchom tools/generate_mqtt_certs.ps1 "
                "lub użyj --insecure (dev).",
                file=sys.stderr,
            )
            sys.exit(1)
        client.tls_set(
            ca_certs=cafile,
            cert_reqs=ssl.CERT_NONE if args.insecure else ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        if args.insecure:
            client.tls_insecure_set(True)

    proto = "mqtts" if use_tls else "mqtt"
    print(f"[symulator] łączenie z {proto}://{args.host}:{args.port} ...")
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    running = True

    def stop(_signum=None, _frame=None):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    print(f"[symulator] węzły: {', '.join(node_ids)} | interval={args.interval}s")
    t0 = time.time()
    try:
        while running:
            now = time.time() - t0
            for prof in profiles:
                payload = sample(prof, now)
                topic = f"weather/{prof.node_id}/data"
                client.publish(topic, json.dumps(payload), qos=args.qos)
                print(
                    f"  -> {topic}  T={payload['temperature']:.2f}°C "
                    f"d={payload['distance']:.2f}cm  L={payload['lux']:.1f}lx"
                )
            time.sleep(args.interval)
    finally:
        client.loop_stop()
        client.disconnect()
        print("[symulator] zakończono.")


if __name__ == "__main__":
    main()
