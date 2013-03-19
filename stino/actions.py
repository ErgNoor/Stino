#-*- coding: utf-8 -*-
# stino/actions.py

import stino
import zipfile
import os

def changeArduinoRoot(arduino_root):
	pre_arduino_root = stino.const.settings.get('arduino_root')
	stino.arduino_info.setArduinoRoot(arduino_root)
	stino.arduino_info.genVersion()
	version_text = stino.arduino_info.getVersionText()
	log_text = 'Arduino %s is found at %s.\n' % (version_text, arduino_root)
	stino.log_panel.addText(log_text)

	if arduino_root != pre_arduino_root:
		stino.arduino_info.update()
		stino.cur_menu.fullUpdate()
		stino.const.settings.set('full_compilation', True)
		stino.const.save_settings()

def changeSketchbookRoot(sketchbook_root):
	sketchbook_root = stino.utils.getInfoFromKey(sketchbook_root)[1]
	pre_sketchbook_root = stino.const.settings.get('sketchbook_root')
	stino.arduino_info.setSketchbookRoot(sketchbook_root)
	log_text = 'Sketchbook folder have switched to %s.\n' % sketchbook_root
	stino.log_panel.addText(log_text)

	if sketchbook_root != pre_sketchbook_root:
		stino.arduino_info.sketchbookUpdate()
		stino.cur_menu.update()

def updateSerialMenu():
	stino.cur_menu.update()

def getArchiveFolderPath(zip_folder_path, sketch_folder_path):
	base_path = sketch_folder_path + os.path.sep
	all_file_list = stino.osfile.findAllFiles(sketch_folder_path)
	all_file_list = [file_path.replace(base_path, '') for file_path in all_file_list]

	zip_folder_path = stino.utils.getInfoFromKey(zip_folder_path)[1]
	sketch_name = stino.src.getSketchNameFromFolder(sketch_folder_path)
	zip_file_name = sketch_name + '.zip'
	zip_file_path = os.path.join(zip_folder_path, zip_file_name)
	opened_zipfile = zipfile.ZipFile(zip_file_path, 'w' ,zipfile.ZIP_DEFLATED)
	os.chdir(sketch_folder_path)
	for cur_file in all_file_list:
		opened_zipfile.write(cur_file)
	opened_zipfile.close()

	text = 'Writing %s completed.\n' % zip_file_path
	stino.log_panel.addText(text)