# discover_hid.py
from zeroconf import Zeroconf, ServiceBrowser
import time

class Listener:
    def add_service(self, zc, service_type, name):
        info = zc.get_service_info(service_type, name)
        if info:
            print(f"Trouvé: {name} -> {info.parsed_addresses()} port {info.port}")
    update_service = add_service
    def remove_service(self, zc, service_type, name):
        pass

zc = Zeroconf()
ServiceBrowser(zc, "_hid._udp.local.", Listener())
print("écoute pendant 10s...")
time.sleep(10)
zc.close()
print("Terminé.")