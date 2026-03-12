# Протокол взаимодействия PC Monitor

## UDP (порт 45454)

### Broadcast от сервера → ESP8266

**Запрос обнаружения:**
```json
{ "type": "discover_request" }
```

### Broadcast от ESP8266 → сервер (каждые 5с)

**Beacon:**
```json
{
  "type": "pc_monitor_beacon",
  "device_id": "esp8266_A4B1C2",
  "mac": "A4:B1:C2:D3:E4:F5",
  "display": "LCD 20x4",
  "firmware": "1.0.0",
  "bound_to": "DESKTOP-GAMING",
  "bound_pc_id": "uuid-1234-abcd"
}
```
`bound_to` и `bound_pc_id` — пустые строки если не привязано.

### Unicast от сервера → ESP8266 (команды привязки)

**Привязать:**
```json
{ "type": "bind", "pc_id": "uuid-...", "pc_name": "DESKTOP-GAMING" }
```

**Перепривязать (force):**
```json
{ "type": "rebind", "pc_id": "uuid-...", "pc_name": "DESKTOP-NEW" }
```

**Отвязать:**
```json
{ "type": "unbind" }
```

**Ответ ESP8266:**
```json
{ "status": "ok" }
{ "status": "error", "message": "..." }
```

---

## HTTP REST (порт 8080)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/sensors` | Список доступных датчиков |
| GET | `/api/data` | Текущие значения датчиков |
| GET | `/api/templates` | Список шаблонов |
| GET | `/api/templates/{name}` | Получить шаблон |
| POST | `/api/templates` | Создать/обновить шаблон |
| DELETE | `/api/templates/{name}` | Удалить шаблон |
| GET | `/api/devices` | Привязанные устройства |
| GET | `/api/devices/discovered` | Обнаруженные в сети |
| POST | `/api/bind` | Привязать устройство |
| POST | `/api/bind/confirm` | Перепривязать (force) |
| DELETE | `/api/devices/{id}` | Отвязать |
| PATCH | `/api/devices/{id}` | Обновить alias/шаблон |

---

## WebSocket `ws://host:8080/ws/data`

### Сервер → ESP8266 (стрим данных)

```json
{
  "timestamp": 1741689600,
  "sensors": {
    "cpu_temp":  { "value": 65.0,  "unit": "°C",  "label": "CPU Temp" },
    "gpu_temp":  { "value": 72.0,  "unit": "°C",  "label": "GPU Temp" },
    "cpu_load":  { "value": 45.0,  "unit": "%",   "label": "CPU Load" },
    "gpu_load":  { "value": 98.0,  "unit": "%",   "label": "GPU Load" },
    "fps":       { "value": 120.0, "unit": "FPS", "label": "FPS" },
    "fps_1low":  { "value": 87.0,  "unit": "FPS", "label": "1% Low" },
    "ram_used":  { "value": 14.2,  "unit": "GB",  "label": "RAM" },
    "gpu_power": { "value": 180.0, "unit": "W",   "label": "GPU Power" }
  }
}
```

### Шаблон страниц (передаётся при подключении)

```json
{
  "type": "template",
  "name": "Gaming",
  "refresh_ms": 1000,
  "pages": [
    { "duration_s": 5, "rows": ["cpu_temp", "gpu_temp", "fps", "fps_1low"] },
    { "duration_s": 5, "rows": ["cpu_load", "gpu_load", "ram_used", "gpu_power"] }
  ]
}
```

---

## Форматы файлов конфигурации

### ESP8266: /data/config.json
```json
{
  "wifi_ssid": "MyNetwork",
  "wifi_pass": "password",
  "server_ip": "192.168.1.100",
  "server_port": 8080,
  "ap_ssid": "PC-Monitor",
  "ap_pass": "12345678"
}
```

### ESP8266: /data/binding.json
```json
{
  "bound": true,
  "pc_id": "uuid-1234-abcd",
  "pc_name": "DESKTOP-GAMING",
  "bound_at": 1741689600
}
```

### Сервер: data/server_config.json
```json
{
  "pc_id": "uuid-1234-abcd",
  "pc_name": "DESKTOP-GAMING",
  "port": 8080,
  "refresh_ms": 1000,
  "udp_beacon_port": 45454
}
```

### Сервер: data/devices.json
```json
{
  "devices": [
    {
      "device_id": "esp8266_A4B1C2",
      "mac": "A4:B1:C2:D3:E4:F5",
      "display": "LCD 20x4",
      "alias": "Монитор на столе",
      "active_template": "Gaming",
      "last_seen": 1741689600
    }
  ]
}
```
