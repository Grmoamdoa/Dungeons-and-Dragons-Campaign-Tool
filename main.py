# main.py (Corrected Pygame Initialization)
import sys
import pygame # Import Pygame (still needed for pygame.mixer)
from PyQt6.QtWidgets import QApplication
from ui.dialog_theme import install_readable_popup_theme
from ui.main_window import MainWindow

if __name__ == "__main__":
    # --- Initialize ONLY Pygame Mixer ---
    mixer_init_error = None
    try:
        # pygame.init() # DO NOT CALL THIS - it initializes all pygame modules
        pygame.mixer.init() # Initialize ONLY the mixer module
        print("Pygame Mixer initialized successfully.")
    except pygame.error as e:
        mixer_init_error = str(e)
        print(f"Error initializing Pygame Mixer: {e}")
        # Decide if the app should exit or continue without audio
        # For a DM tool, audio is important, but maybe not a fatal error.
        # Consider a QMessageBox here to inform the user if it fails.
        # sys.exit(1) # Optional: Exit if audio is absolutely critical
    # --- End Initialization ---

    app = QApplication(sys.argv)
    install_readable_popup_theme(app)
    
    # It's good practice to set application name and version if not done elsewhere
    app.setApplicationName("D&D Campaign Presenter")
    app.setApplicationVersion("1.2.4")

    main_window = MainWindow(audio_startup_error=mixer_init_error)
    main_window.show()
    exit_code = app.exec()

    # --- Quit ONLY Pygame Mixer when app exits ---
    if pygame.mixer.get_init(): # Check if mixer was successfully initialized
        pygame.mixer.quit()
        print("Pygame Mixer quit.")
    # pygame.quit() # DO NOT CALL THIS if only mixer was init'd
    # --- End Quit ---

    sys.exit(exit_code)
