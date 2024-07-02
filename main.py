import traceback
import eel
import winreg
import subprocess
import os
import ctypes
import logging
import sys
import configparser
import socket

LOG_FILE = 'app.log'
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', filename=LOG_FILE, filemode='a')

config = configparser.ConfigParser()

eel.init('web')

config.read('config.ini')

if config.has_section('Config') and config.has_option('Config', 'interfaceValue') and config.has_option('Config','IPAddress') and config.has_option(
        'Config', 'PortNumber') and config.has_option('Config', 'IgnoredPorts'):
    eel.parseValues(config['Config']['interfaceValue'], config['Config']['IPAddress'], config['Config']['PortNumber'],
                    config['Config']['IgnoredPorts'])


def is_winpcap_installed():
    try:
        registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\WinPcap", 0, winreg.KEY_READ)
        winreg.CloseKey(registry_key)
        logging.info(f"WinPcap installed")
        return True
    except FileNotFoundError:
        logging.info(f"WinPcap not installed")
        return False
    except Exception as e:
        logging.info(f"An error occurred: {e}")
        return False


@eel.expose
def check_winpcap():
    if is_winpcap_installed():
        eel.show_monitor_page()
    else:
        eel.launch_installer()


@eel.expose
def launch_installer():
    try:
        installer_path = os.path.join(os.path.dirname(__file__), "WinPcap_4_1_3.exe")
        subprocess.run(['powershell', 'Start-Process', installer_path, '-Verb', 'runAs'], check=True)
        if is_winpcap_installed():
            eel.show_monitor_page()
            logging.info(f"WinPcap driver installed")
    except subprocess.CalledProcessError as e:
        eel.show_alert_dialog(f"An error occurred while launching the installer: {e}")
        logging.info(f"An error occurred while launching the installer: {e}")
    except Exception as e:
        eel.show_alert_dialog(f"An unexpected error occurred: {e}")
        logging.info(f"An unexpected error occurred: {e}")


def is_admin():
    try:
        return os.getuid() == 0 or ctypes.windll.shell32.IsUserAnAdmin()
    except AttributeError:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False


def run_as_admin(script):
    if sys.version_info[0] == 3 and sys.version_info[1] >= 5:
        subprocess.run(['powershell', 'Start-Process', sys.executable, '-ArgumentList', script, '-Verb', 'runAs'],
                       check=True)
    else:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, script, None, 1)


@eel.expose
def start_monitoring(ip_address, port_number, ignored_ports):
    ignored_ports_list = ignored_ports.split(',')
    ignored_ports_conditions = " and not port ".join(ignored_ports_list)

    bat_file = os.path.join(os.path.dirname(__file__), "run_windump.bat")

    with open(bat_file, 'w') as f:
        f.write(f"@echo off\n")
        f.write(
            f"windump -i1 -w - not port {port_number} and not {ignored_ports_conditions} and not arp and not rarp and not icmp and not broadcast | socat - TCP:{ip_address}:{port_number},forever,retry,interval=1\n")

    command = f'powershell -Command "Start-Process -FilePath \'{bat_file}\' -WindowStyle Hidden"'

    if not is_admin():
        run_as_admin(__file__)
    else:
        subprocess.run(command, shell=True, check=True)
    if not is_admin():
        print("Not running with admin privileges!")
        logging.info("Not running with admin privileges!")
    else:
        print("Running in admin privileges!")
        logging.info("Running in admin privileges!")


def check_winpcap_installed():
    system32 = os.path.join(os.environ['SystemRoot'], 'System32')
    winpcap_dll = os.path.join(system32, 'Packet.dll')
    return os.path.exists(winpcap_dll)


def run_as_admin1(script, params):
    params = ' '.join([f'"{param}"' for param in params])
    subprocess.run(
        ['powershell', 'Start-Process', sys.executable, '-ArgumentList', f'"{script} {params}"', '-Verb', 'runAs'],
        check=True)


@eel.expose
def check_ip_port(interfaceValue, ip_address, port_number, ignored_ports):
    try:
        with socket.create_connection((ip_address, int(port_number)), timeout=5) as sock:
            eel.ipValid()
            start_service(interfaceValue, ip_address, port_number, ignored_ports)
            logging.info("IP is valid")
            return True
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        print(f"Failed to connect to {ip_address} on port {port_number}: {e}")
        eel.ipInValid()
        logging.info(f"Failed to connect to {ip_address} on port {port_number}: {e} | Invalid IP")
        return False


@eel.expose
def start_service(interfaceValue, ip_address, port_number, ignored_ports):
    if not check_winpcap_installed():
        eel.show_alert("WinPcap is not installed. Please install it first.")
        logging.info("WinPcap is not installed")
        return

    ignored_ports_list = ignored_ports.split(',')
    ignored_ports_conditions = " and not port ".join(ignored_ports_list)

    windump_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "executables", "windump.exe"))
    socat_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "executables", "socat.exe"))
    nssm_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "executables", "nssm.exe"))

    command = f'{windump_path} -i{interfaceValue} -w - not port {ignored_ports_conditions} | {socat_path} - TCP:{ip_address}:{port_number},forever,retry,interval=1'

    print(command)

    config['Config'] = {'interfaceValue': interfaceValue, 'IPAddress': ip_address, 'PortNumber': port_number,
                        'IgnoredPorts': str(ignored_ports).replace(port_number + ",", "")}

    with open('config.ini', 'w') as configfile:
        config.write(configfile)

    service_name = "SocatService"
    if not is_admin():
        subprocess.run(['powershell', 'Start-Process', sys.executable, '-ArgumentList', command, '-Verb', 'runAs'],
                       check=True)
        return

    try:
        install_result = subprocess.run([nssm_path, 'install', service_name, 'cmd.exe', '/c', command])
        if install_result.returncode == 0:
            logging.info("Service is installed")
            print("Service installed successfully.")
        else:
            logging.info("Failed to install service")
            print(f"Failed to install service, A service with same name might already exists: {install_result.stderr}")
            return

        start_result = subprocess.run([nssm_path, 'start', service_name])
        if start_result.returncode == 0:
            print("Service started successfully.")
            logging.info("Service started successfully.")
        else:
            print(f"Error code: {start_result.returncode}")
            print(f"Failed to start service: {start_result} | {start_result.stderr}")
            logging.info(f"Service start failed Error code: {start_result.returncode} | {start_result} | {start_result.stderr}")
            return
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        print(f"Output: {e.output}")
        print(f"Error: {e.stderr}")
        logging.info(f"Error occurred: {e} | Output: {e.output} | Error: {e.stderr}")


@eel.expose
def is_service_running(service_name="SocatService"):
    try:
        result = subprocess.run(['sc', 'query', service_name], capture_output=True, text=True)
        if 'RUNNING' in result.stdout:
            return "Running"
        elif 'PAUSED' in result.stdout:
            return "Paused"
        else:
            return "Removed/Stopped"
    except Exception as e:
        print(f"An error occurred: {e}")
        return "Unknown"


@eel.expose
def get_windump_interfaces():
    windump_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "executables", "windump.exe"))

    try:
        result = subprocess.run([windump_path, '-D'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        if result.returncode == 0:
            logging.info("Interfaces retrieved successfully.")
            return result.stdout
        else:
            logging.info(f"Failed to get interfaces: {result.stderr}")
            print(f"Failed to get interfaces: {result.stderr}")
            return None
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        print(f"Output: {e.output}")
        print(f"Error: {e.stderr}")
        logging.info(f"Error occurred: {e} | Output: {e.output} | Error: {e.stderr}")
        return None


@eel.expose
def delete_service(service_name="SocatService"):
    nssm_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "executables", "nssm.exe"))

    #if not is_admin():
    #run_as_admin(__file__, [service_name])
    #return

    try:
        stop_result = subprocess.run([f"{nssm_path}", 'stop', service_name], check=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        if stop_result.returncode == 0:
            print("Service stopped successfully.")
            logging.info("Service stopped successfully.")
        else:
            print(f"Failed to stop service: {stop_result.stderr}")
            logging.info(f"Failed to stop service: {stop_result.stderr}")
            return

        delete_result = subprocess.run([f"{nssm_path}", 'remove', service_name, 'confirm'], check=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if delete_result.returncode == 0:
            print("Service deleted successfully.")
            logging.info("Service deleted successfully.")
        else:
            print(f"Failed to delete service: {delete_result.stderr}")
            logging.info(f"Failed to delete service: {delete_result.stderr}")
            return
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        print(f"Output: {e.output}")
        print(f"Error: {e.stderr}")
        logging.info(f"Error occurred: {e} | Output: {e.output} | Error: {e.stderr}")


def get_screen_size():
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()  # Hide the root window

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    return screen_width, screen_height


def center_window(window_width, window_height):
    screen_width, screen_height = get_screen_size()

    center_x = int((screen_width - window_width) / 2)
    center_y = int((screen_height - window_height) / 2)

    return center_x, center_y


window_width = 600
window_height = 740

center_x, center_y = center_window(window_width, window_height)

"""def run_as_admin():
    if ctypes.windll.shell32.IsUserAnAdmin() == 0:
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        if result > 32:
            if not is_admin():
                print("Is not admin privileges!")
            else:
                print("Is admin privileges!")
            eel.start('main.html', size=(500, 500), position=(center_x, center_y))
        else:
            print(f"Error: Failed to start with admin privileges. Error code: {result}")
    else:
        print("Already running as admin")"""


#run_as_admin()

@eel.expose
def get_windump_interfaces_exposed():
    return get_windump_interfaces()


def restart_as_admin():
    try:
        if getattr(sys, 'frozen', False):
            executable = os.path.abspath(sys.executable)
            logging.info("Running as executable")
        else:
            executable = os.path.abspath(__file__)
            logging.info("Running as script")

        params = ' '.join([f'"{param}"' for param in sys.argv])
        shell32 = ctypes.windll.shell32
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()

        result = shell32.ShellExecuteW(hwnd, "runas", executable, params, None, 1)

        if result <= 32:
            error_messages = {
                0: "The operating system is out of memory or resources.",
                2: "The specified file was not found.",
                3: "The specified path was not found.",
                5: "Access is denied.",
                27: "The drive name is invalid.",
                32: "The file is being used by another program.",
                1155: "The specified dynamic-link library was not found."
            }
            error_message = error_messages.get(result, f"Unknown error: {result}")
            logging.info(f"Failed to elevate privileges, error code: {result} - {error_message}")
            print(f"Failed to elevate privileges, error code: {result} - {error_message}")
            sys.exit(1)

        sys.exit()
    except Exception as e:
        print(f"Exception occurred while trying to restart as admin: {e}")
        logging.info(f"Exception occurred while trying to restart as admin: {e}")
        traceback.print_exc()
        # sys.exit(1)


if not is_admin():
    if not is_admin():
        logging.info("Not running as admin")
        restart_as_admin()

    # print("Running with admin privileges.")

eel.start('main.html', size=(600, 740), position=(center_x, center_y))
