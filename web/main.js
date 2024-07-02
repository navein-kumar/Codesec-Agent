// Function to call the Python function check_winpcap
function checkWinPcap() {
    eel.check_winpcap();
}

// Function to call the Python function install_winpcap
function installWinPcap() {
    eel.install_winpcap();
}

eel.expose(launch_installer)
function launch_installer() {
    document.getElementById("notInstalled").style.display = "block";
}

// Expose the alert dialog function to Python
eel.expose(show_alert_dialog);
function show_alert_dialog(message) {
    alert(message);
}
