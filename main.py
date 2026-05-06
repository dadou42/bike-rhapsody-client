"""
Bike Rhapsody Mac Client — point d'entrée.
"""
import sys
import os

# Ajouter le répertoire racine au path (utile hors bundle PyInstaller)
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon


def main():
    # macOS : utiliser la barre de menus native
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("Bike Rhapsody Client")
    app.setOrganizationName("BikeRhapsody")
    app.setOrganizationDomain("bike-rhapsody.fr")

    # Bootstrap (DB, client HTTP, session)
    from app.bootstrap import bootstrap
    settings = bootstrap()

    # Fenêtre principale
    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
