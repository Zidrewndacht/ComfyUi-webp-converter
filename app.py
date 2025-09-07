import json
import os
from PyQt5.QtWidgets import (QApplication, QCheckBox, QSlider, QWidget,
                             QVBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox, QSpinBox, QHBoxLayout)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PIL import Image
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import sys


class ConversionWorker(QThread):
    progress = pyqtSignal(int)  # Signal to update progress
    finished_signal = pyqtSignal(list, list)  # Signal when all conversions are done
    error_signal = pyqtSignal(str)  # Signal for errors

    def __init__(self, file_paths, output_dir, quality, keep_workflow, use_same_folder):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.quality = quality
        self.keep_workflow = keep_workflow
        self.use_same_folder = use_same_folder
        self.cpu_count = multiprocessing.cpu_count()

    def run(self):
        try:
            if self.keep_workflow:
                renamed_files, success = self.convert_images_to_webp_with_metadata()
            else:
                renamed_files, success = self.convert_images_to_webp()
            
            self.finished_signal.emit(renamed_files, success)
        except Exception as e:
            self.error_signal.emit(str(e))

    def convert_images_to_webp(self):
        renamed_files = []
        success = []

        def convert_single_image(img_path):
            try:
                img = Image.open(img_path)
                filename = os.path.basename(img_path)
                
                # Determine output directory
                if self.use_same_folder:
                    output_dir = os.path.dirname(img_path)
                else:
                    output_dir = self.output_dir
                
                output_filename = os.path.splitext(filename)[0] + '.webp'
                output_path = os.path.join(output_dir, output_filename)

                # Create directory if it doesn't exist
                os.makedirs(output_dir, exist_ok=True)

                # Check if file already exists
                if os.path.exists(output_path):
                    base_name = os.path.splitext(output_filename)[0]
                    counter = 1
                    # Find a new name by appending a number if it already exists
                    while os.path.exists(output_path):
                        output_filename = f"{base_name}_{counter}.webp"
                        output_path = os.path.join(output_dir, output_filename)
                        counter += 1

                    # Keep track of renamed files
                    renamed_files.append(f"{filename} -> {output_filename}")

                # Save the image as WebP
                img.save(output_path, 'webp', quality=self.quality)
                return output_path
            except Exception as e:
                raise Exception(f'Failed to convert {filename}: {e}')

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.cpu_count) as executor:
            futures = [executor.submit(convert_single_image, img_path) for img_path in self.file_paths]
            
            for i, future in enumerate(futures):
                try:
                    result = future.result()
                    success.append(result)
                    self.progress.emit(int((i + 1) / len(futures) * 100))
                except Exception as e:
                    self.error_signal.emit(str(e))

        return renamed_files, success

    def convert_images_to_webp_with_metadata(self):
        renamed_files = []
        success = []

        def convert_single_image_with_metadata(img_path):
            try:
                img = Image.open(img_path)
                filename = os.path.basename(img_path)
                
                # Determine output directory
                if self.use_same_folder:
                    output_dir = os.path.dirname(img_path)
                else:
                    output_dir = self.output_dir
                
                output_filename = os.path.splitext(filename)[0] + '.webp'
                output_path = os.path.join(output_dir, output_filename)

                # Create directory if it doesn't exist
                os.makedirs(output_dir, exist_ok=True)

                # Check if file already exists
                if os.path.exists(output_path):
                    base_name = os.path.splitext(output_filename)[0]
                    counter = 1
                    # Find a new name by appending a number if it already exists
                    while os.path.exists(output_path):
                        output_filename = f"{base_name}_{counter}.webp"
                        output_path = os.path.join(output_dir, output_filename)
                        counter += 1

                    # Keep track of renamed files
                    renamed_files.append(f"{filename} -> {output_filename}")

                # Saving
                if filename.lower().endswith(".png"):
                    # get info
                    try:
                        dict_of_info = img.info.copy()
                        # Remove nodes that may cause problems
                        try:
                            c = json.loads(dict_of_info.get("workflow"))
                            nodes: list = c.get('nodes')
                            for n in nodes:
                                if n['type'] == 'LoraInfo':
                                    nodes.remove(n)
                            dict_of_info['workflow'] = json.dumps(c)
                        except Exception as e:
                            print(e)
                            pass

                        # Saving
                        img_exif = img.getexif()
                        user_comment = dict_of_info.get("workflow", "")
                        img_exif[0x010e] = "Workflow:" + user_comment
                        img.convert("RGB").save(output_path, lossless=False,
                                                quality=self.quality, webp_method=6,
                                                exif=img_exif)
                        return output_path
                    except Exception as e:
                        raise Exception(f'Failed to convert {filename} with ComfyUI workflow: {e}')
                else:
                    raise Exception(f'Failed to convert {filename} with ComfyUI workflow.\n'
                                   f'Consider using png files with workflow or uncheck keep ComfyUI workflow')
            except Exception as e:
                raise Exception(f'Failed to convert {filename}: {e}')

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.cpu_count) as executor:
            futures = [executor.submit(convert_single_image_with_metadata, img_path) for img_path in self.file_paths]
            
            for i, future in enumerate(futures):
                try:
                    result = future.result()
                    success.append(result)
                    self.progress.emit(int((i + 1) / len(futures) * 100))
                except Exception as e:
                    self.error_signal.emit(str(e))

        return renamed_files, success


class ImageConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Image to WebP Converter')
        self.setGeometry(800, 400, 450, 350)

        layout = QVBoxLayout()

        # Add check box for keeping workflow
        self.checkbox = QCheckBox('Keep ComfyUI workflow', self)
        layout.addWidget(self.checkbox)

        # Add check box for saving in same folder
        self.same_folder_checkbox = QCheckBox('Save in same folder as original', self)
        self.same_folder_checkbox.stateChanged.connect(self.toggle_output_selection)
        layout.addWidget(self.same_folder_checkbox)

        # Label for file selection
        self.file_label = QLabel('Select Images to Convert:', self)
        layout.addWidget(self.file_label)

        # Button for file selection
        self.file_button = QPushButton('Browse Images', self)
        self.file_button.clicked.connect(self.select_images)
        layout.addWidget(self.file_button)

        # Button for folder selection
        self.folder_button = QPushButton('Browse Folder (Recursive)', self)
        self.folder_button.clicked.connect(self.select_folder)
        layout.addWidget(self.folder_button)

        # Output directory selection
        self.output_label = QLabel('Select Output Directory:', self)
        layout.addWidget(self.output_label)

        # Button for output directory selection
        self.output_button = QPushButton('Browse Output Directory', self)
        self.output_button.clicked.connect(self.select_output_directory)
        layout.addWidget(self.output_button)

        # CPU count selection
        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(QLabel('Number of threads:'))
        self.cpu_spinbox = QSpinBox()
        self.cpu_spinbox.setRange(1, multiprocessing.cpu_count())
        self.cpu_spinbox.setValue(multiprocessing.cpu_count())
        cpu_layout.addWidget(self.cpu_spinbox)
        layout.addLayout(cpu_layout)

        # Input for quality selection
        self.quality_label = QLabel('Enter WebP Quality (1-100): 87', self)
        layout.addWidget(self.quality_label)

        self.quality_slider = QSlider(Qt.Horizontal, self)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(87)  # Default quality
        layout.addWidget(self.quality_slider)
        self.quality_slider.valueChanged.connect(self.update_quality_label)

        # Convert button
        self.convert_button = QPushButton('Convert to WebP', self)
        self.convert_button.clicked.connect(self.convert_images)
        layout.addWidget(self.convert_button)

        # Progress label
        self.progress_label = QLabel('', self)
        layout.addWidget(self.progress_label)

        self.setLayout(layout)

        # Initialize variables
        self.file_paths = []
        self.output_dir = ""
        self.worker = None

    def toggle_output_selection(self, state):
        # Enable/disable output directory selection based on checkbox
        enabled = state == Qt.Unchecked
        self.output_button.setEnabled(enabled)
        self.output_label.setEnabled(enabled)

    def update_quality_label(self):
        current_value = self.quality_slider.value()
        self.quality_label.setText(f'Enter WebP Quality (1-100): {current_value}')

    def select_images(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        self.file_paths, _ = QFileDialog.getOpenFileNames(self, 'Select Images', '',
                                                          'Image Files (*.png *.jpg *.jpeg *.bmp *.tiff)',
                                                          options=options)
        if self.file_paths:
            self.file_label.setText(f'Selected {len(self.file_paths)} image(s)')

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder to Convert')
        if folder:
            self.file_paths = []
            # Walk through directory and subdirectories
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                        self.file_paths.append(os.path.join(root, file))
            
            self.file_label.setText(f'Selected {len(self.file_paths)} image(s) from folder and subfolders')

    def select_output_directory(self):
        self.output_dir = QFileDialog.getExistingDirectory(self, 'Select Output Directory')
        if self.output_dir:
            self.output_label.setText(f'Selected Output Directory: {self.output_dir}')

    def convert_images(self):
        # Get quality input and validate
        try:
            quality = self.quality_slider.value()
            if quality < 1 or quality > 100:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, 'Error', 'Please enter a valid quality between 1 and 100.')
            return

        if not self.file_paths:
            QMessageBox.warning(self, 'Error', 'Please select at least one image file or folder.')
            return

        if not self.same_folder_checkbox.isChecked() and (not hasattr(self, 'output_dir') or not self.output_dir):
            QMessageBox.warning(self, 'Error', 'Please select an output directory.')
            return

        # Disable convert button while converting
        self.convert_button.setEnabled(False)
        self.progress_label.setText('Converting...')

        # Create worker thread
        use_same_folder = self.same_folder_checkbox.isChecked()
        self.worker = ConversionWorker(
            self.file_paths, 
            self.output_dir, 
            quality, 
            self.checkbox.isChecked(),
            use_same_folder
        )
        
        self.worker.progress.connect(self.update_progress)
        self.worker.finished_signal.connect(self.conversion_finished)
        self.worker.error_signal.connect(self.conversion_error)
        self.worker.start()

    def update_progress(self, value):
        self.progress_label.setText(f'Converting... {value}%')

    def conversion_finished(self, renamed_files, success):
        # Prepare the message to show to the user
        if renamed_files:
            renamed_files_message = "\n".join(renamed_files)
            QMessageBox.information(self, 'Process Completed',
                                    f'Converted {len(success)} image(s).\nThe output directory contained files '
                                    f'with identical names. \nThe following converted files have been renamed:\n'
                                    f'{renamed_files_message}')
        else:
            QMessageBox.information(self, 'Process Completed',
                                    f'Converted {len(success)} image(s).')

        # Reset the label
        self.file_label.setText('Select Images to Convert:')
        self.progress_label.setText('')
        # Reset convert button
        self.convert_button.setEnabled(True)
        
        # Clear file paths
        self.file_paths = []

    def conversion_error(self, error_message):
        QMessageBox.warning(self, 'Error', f'Conversion failed: {error_message}')
        self.progress_label.setText('')
        self.convert_button.setEnabled(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageConverter()
    window.show()
    sys.exit(app.exec_())