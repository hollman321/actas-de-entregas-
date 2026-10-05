"""Casos GLPI simulados para desarrollo local.

Para agregar un caso, usa la misma estructura y cambia únicamente ``case_number``
junto con los datos del caso. No contiene credenciales ni datos de producción.
"""

MOCK_GLPI_CASES = {
    "45084": {
        "case_number": "45084",
        "user_name": "Hollman Edinson Hoyos Caicedo",
        "document": "1058667310",
        "portfolio": "Tecnologia",
        "site": "Cali",
        "act_type": "Entrega",
        "equipment": {
            "type": "Desktop",
            "brand": "HP",
            "model": "ProDesk 400 G5 SFF",
            "serial": "MXL909330M",
            "processor": "Intel Core i7-8700",
            "ram": "8 GB",
            "disk": "128 GB",
            "operating_system": "Windows 11",
            "inventory_plate": "510",
        },
        "windows_user": "hoyos.hollman",
        "email": "hollman.hoyos@synerjoy.com",
        "helpdesk_access": True,
        "peripherals": {
            "headset": {"brand": "Jabra", "model": "Evolve 20", "inventory_plate": "P-45084-01", "serial": "JAB4508401"},
        },
    },
    "42931": {
        "case_number": "42931",
        "user_name": "Jessica Ximena Lopez Calderon",
        "document": "1058667999",
        "portfolio": "Banco Union",
        "site": "Cali",
        "act_type": "Cambio",
        "equipment": {
            "type": "Desktop",
            "brand": "HP",
            "model": "ProDesk 600 G2 SFF",
            "serial": "2UA61627TD",
            "returned_serial": "MXL94935Y3",
            "processor": "Intel Core i5-6500",
            "ram": "8 GB",
            "disk": "500 GB",
            "operating_system": "Windows 10",
            "inventory_plate": "2257",
        },
        "windows_user": "lopez.jessica",
        "email": "jessica.lopez@synerjoy.com",
        "helpdesk_access": True,
        "peripherals": {
            "keyboard": {"brand": "Logitech", "model": "K120", "inventory_plate": "P-42931-01", "serial": "LOG4293101"},
        },
    },
    "45120": {
        "case_number": "45120",
        "user_name": "Sandra Patricia Carreno Aceros",
        "document": "",
        "portfolio": "Tecnologia",
        "site": "Cali",
        "act_type": "Entrega",
        "equipment": {
            "type": "Desktop",
            "brand": "Lenovo",
            "model": "ThinkCentre M720",
            "serial": "LEN45120PC",
            "processor": "Intel Core i5",
            "ram": "16 GB",
            "disk": "256 GB SSD",
            "operating_system": "Windows 11",
            "inventory_plate": "45120",
        },
        "windows_user": "carreno.sandra",
        "email": "sandra.carreno@synerjoy.com",
        "helpdesk_access": True,
        "peripherals": {
            "mouse": {"brand": "Dell", "model": "MS116", "inventory_plate": "P-45120-01", "serial": "DEL4512001"},
        },
    },
    "45200": {
        "case_number": "45200",
        "user_name": "Cindy Stefania Crespo Garcia",
        "document": "",
        "portfolio": "Tecnologia",
        "site": "Cali",
        "act_type": "Cambio",
        "equipment": {
            "type": "Desktop",
            "brand": "Dell",
            "model": "OptiPlex 3080",
            "serial": "DEL45200PC",
            "returned_serial": "DEL45200OLD",
            "processor": "Intel Core i5",
            "ram": "8 GB",
            "disk": "256 GB SSD",
            "operating_system": "Windows 10",
            "inventory_plate": "45200",
        },
        "windows_user": "crespo.cindy",
        "email": "cindy.crespo@synerjoy.com",
        "helpdesk_access": True,
        "peripherals": {
            "headset": {"brand": "Plantronics", "model": "Blackwire C3220", "inventory_plate": "P-45200-01", "serial": "PLN4520001"},
        },
    },
    "45355": {
        "case_number": "45355",
        "user_name": "Harold Sneider Garzon Aldana",
        "document": "",
        "portfolio": "Tecnologia",
        "site": "Cali",
        "act_type": "Entrega",
        "equipment": {
            "type": "Desktop",
            "brand": "HP",
            "model": "ProDesk 400 G5 SFF",
            "serial": "HP45355PC",
            "processor": "Intel Core i5",
            "ram": "8 GB",
            "disk": "256 GB",
            "operating_system": "Windows 11",
            "inventory_plate": "45355",
        },
        "windows_user": "garzon.harold",
        "email": "harold.garzon@synerjoy.com",
        "helpdesk_access": True,
        "peripherals": {
            "keyboard": {"brand": "HP", "model": "125", "inventory_plate": "P-45355-01", "serial": "HP4535501"},
        },
    },
}


def get_mock_case(case_number):
    normalized = str(case_number).strip().upper().replace("GLPI-", "")
    return MOCK_GLPI_CASES.get(normalized)


def available_mock_cases():
    return sorted(MOCK_GLPI_CASES)
