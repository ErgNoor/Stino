#-*- coding: utf-8 -*-
# stino/compilation.py

import sublime
import threading
import datetime
import time
import os
import re
import subprocess
import shlex
import serial

from stino import const
from stino import osfile
from stino import utils
from stino import src
from stino import stpanel
from stino import arduino
from stino import smonitor

ram_size_dict = {}
ram_size_dict['attiny44'] = '256'
ram_size_dict['attiny45'] = '256'
ram_size_dict['attiny84'] = '512'
ram_size_dict['attiny85'] = '512'
ram_size_dict['atmega8'] = '1024'
ram_size_dict['atmega168'] = '1024'
ram_size_dict['atmega328p'] = '1024'
ram_size_dict['atmega1280'] = '4096'
ram_size_dict['atmega2560'] = '8196'
ram_size_dict['atmega32u4'] = '2560'
ram_size_dict['at90usb162'] = '512'
ram_size_dict['at90usb646'] = '4096'
ram_size_dict['at90usb1286'] = '8192'
ram_size_dict['cortex-m3'] = '98304'
ram_size_dict['cortex-m4'] = '16384'

def formatNumber(number):
	length = len(number)
	number_str = number[::-1]
	seq = 1
	new_number = ''
	for digit in number_str:
		if seq % 3 == 0:
			if seq != length:
				digit = ',' + digit
		new_number = digit + new_number
		seq += 1
	return new_number

def findSrcFiles(path):
	file_path_list = []
	for (cur_path, sub_dirs, files) in os.walk(path):
		for cur_file in files:
			cur_ext = os.path.splitext(cur_file)[1]
			if cur_ext in src.src_ext_list:
				cur_file_path = os.path.join(cur_path, cur_file)
				cur_file_path = cur_file_path.replace(os.path.sep, '/')
				file_path_list.append(cur_file_path)
	return file_path_list

def findLibrarySrcFiles(lib_path):
	file_path_list = []
	for (cur_path, sub_dirs, files) in os.walk(lib_path):
		if 'examples' in cur_path:
			continue
		for cur_file in files:
			cur_ext = os.path.splitext(cur_file)[1]
			if cur_ext in src.src_ext_list:
				cur_file_path = os.path.join(cur_path, cur_file)
				cur_file_path = cur_file_path.replace(os.path.sep, '/')
				file_path_list.append(cur_file_path)
	return file_path_list

def findMainSrcFile(src_path_list):
	main_src_path = ''
	main_src_number = 0
	for src_path in src_path_list:
		src_text = osfile.readFileText(src_path)
		if src.isMainSrcText(src_text):
			main_src_path = src_path
			main_src_number += 1
	return (main_src_number, main_src_path)

def getPlatformFilePath(platform, board):
	platform_file_path = ''
	platform_file = ''
	if 'Arduino AVR' in platform:
		platform_file = 'arduino_avr.txt'
	elif 'teensy' in platform:
		if '3.0' in board:
			platform_file = 'teensy_arm.txt'
		else:
			platform_file = 'teensy_avr.txt'
	if platform_file:
		platform_file_path = os.path.join(const.compilation_script_root, platform_file)
	return platform_file_path

def getBoardInfoBlock150(board_file_path, board):
	board_info_block = []
	lines = osfile.readFileLines(board_file_path)
	info_block_list = utils.splitToBlocks(lines, sep = '.name')
	for info_block in info_block_list:
		for line in info_block:
			if '.name' in line:
				(key, board_name) = utils.getKeyValue(line)
			if '.container' in line:
				(key, board_name) = utils.getKeyValue(line)
				break
		if board_name == board:
			board_info_block = info_block
			break
	return board_info_block

def getBoardInfoBlock(board_file_path, board):
	board_info_block = []
	lines = osfile.readFileLines(board_file_path)
	info_block_list = utils.splitToBlocks(lines, sep = '.name', none_sep = 'menu.')
	for info_block in info_block_list:
		board_name_line = info_block[0]
		(key, board_name) = utils.getKeyValue(board_name_line)
		if board_name == board:
			board_info_block = info_block
			break
	return board_info_block

def getBoardCommonInfoBlock(board_info_block):
	board_common_info_block = []
	for line in board_info_block:
		if 'menu.' in line:
			break
		board_common_info_block.append(line)
	return board_common_info_block

def getBoardTypeInfoBlock(board_info_block, board_type):
	board_type_info_block = []
	for line in board_info_block:
		if board_type in line:
			board_type_info_block.append(line)
	return board_type_info_block

def genOptionInfoBlockList(info_block):
	block_list = utils.splitToBlocks(info_block, sep = '.name', key_length = 4)
	name_key_list = []
	for block in block_list:
		name_line = block[0]
		(key, value) = utils.getKeyValue(name_line)
		key = key.replace('.name', '.')
		name_key_list.append(key)

	option_info_block_list = []
	for name_key in name_key_list:
		option_info_block = []
		for line in info_block:
			if name_key in line:
				option_info_block.append(line)
		option_info_block_list.append(option_info_block)
	return option_info_block_list

def removeOptionInfoFromBlock(board_info_block, board_type_value_dict):
	info_block_list = []
	board_common_info_block = getBoardCommonInfoBlock(board_info_block)
	info_block_list.append(board_common_info_block)

	for board_type in board_type_value_dict:
		value = board_type_value_dict[board_type]
		board_type_info_block = getBoardTypeInfoBlock(board_info_block, board_type)
		option_info_block_list = genOptionInfoBlockList(board_type_info_block) 
		for option_info_block in option_info_block_list:
			name_line = option_info_block[0]
			(key, name) = utils.getKeyValue(name_line)
			if name == value:
				info_block_list.append(option_info_block)
				break
	return info_block_list                                                                                               

def genBoardInfoBlockList(board_file_path, board, board_type_value_dict):
	info_block_list = []
	if arduino.isBoard150(board_file_path):
		board_info_block = getBoardInfoBlock150(board_file_path, board)
		info_block_list.append(board_info_block)
	else:
		board_info_block = getBoardInfoBlock(board_file_path, board)
		if board_type_value_dict:
			info_block_list = removeOptionInfoFromBlock(board_info_block, board_type_value_dict)
		else:
			info_block_list.append(board_info_block)
	return info_block_list

def genInfoDictFromBlock(info_block):
	info_key_list = []
	info_dict = {}
	name_line = info_block[0]
	(name_key, name) = utils.getKeyValue(name_line)
	name_key = name_key.replace('.name', '.')
	if name_key[-1] != '.':
		name_key += '.'
	for line in info_block[1:]:
		(key, value) = utils.getKeyValue(line)
		key = key.replace(name_key, '')
		info_key_list.append(key)
		info_dict[key] = value
	return (info_key_list, info_dict)

def getBoardInfoDict(info_block_list):
	board_info_key_list = []
	board_info_dict = {}
	for info_block in info_block_list:
		(info_key_list, info_dict) = genInfoDictFromBlock(info_block)
		for info_key in info_key_list:
			if info_key in board_info_key_list:
				board_info_key_list.remove(info_key)
			board_info_key_list.append(info_key)
			board_info_dict[info_key] = info_dict[info_key]
	return (board_info_key_list, board_info_dict)

def parseBoradInfo(board_file_path, board, board_type_value_dict):
	info_block_list = genBoardInfoBlockList(board_file_path, board, board_type_value_dict)
	(board_info_key_list, board_info_dict) = getBoardInfoDict(info_block_list)
	return (board_info_key_list, board_info_dict)

def getProgrammerInfoBlock(programmer_file_path, programmer):
	lines = osfile.readFileLines(programmer_file_path)
	info_block_list = utils.splitToBlocks(lines, sep = '.name')
	for info_block in info_block_list:
		programmer_name_line = info_block[0]
		(key, programmer_name) = utils.getKeyValue(programmer_name_line)
		if programmer_name == programmer:
			programmer_info_block = info_block
			break
	return programmer_info_block

def parseProgrammerInfo(programmer_file_path, programmer):
	programmer_info_dict = {}
	programmer_info_key_list = []
	if programmer_file_path:
		programmer_info_block = getProgrammerInfoBlock(programmer_file_path, programmer)
		(programmer_info_key_list, programmer_info_dict) = genInfoDictFromBlock(programmer_info_block)
	return (programmer_info_key_list, programmer_info_dict)

def regulariseToolsKey(key):
	info_list = key.split('.')
	new_key = ''
	for info in info_list[2:]:
		new_key += info
		new_key += '.'
	new_key = new_key[:-1]
	new_key = new_key.replace('params.', '')
	return new_key

def parsePlatformInfo(platform_file_path):
	platform_info_key_list = []
	platform_info_dict = {}
	lines = osfile.readFileLines(platform_file_path)
	for line in lines:
		line = line.strip()
		if line and (not '#' in line):
			(key, value) = utils.getKeyValue(line)
			if 'tools.' in key:
				key = regulariseToolsKey(key)
			platform_info_key_list.append(key)
			platform_info_dict[key] = value
	return (platform_info_key_list, platform_info_dict)

def regulariseDictValue(info_dict, info_key_list):
	pattern_text = r'\{\S+?}'
	for info_key in info_key_list:
		info_value = info_dict[info_key]
		key_list = re.findall(pattern_text, info_value)
		if key_list:
			key_list = [key[1:-1] for key in key_list]
			for key in key_list:
				replace_text = '{' + key + '}'
				if key in info_dict:
					value = info_dict[key]
				else:
					value = ''
				info_value = info_value.replace(replace_text, value)
			info_dict[info_key] = info_value
	return info_dict

def genCommandArgs(command):
	command = command.encode(const.sys_encoding)
	if const.sys_platform == 'windows':
		command = command.replace('/"', '"')
		command = command.replace('/', os.path.sep)
		std_args = '"' + command + '"'
	else:
		args = shlex.split(command)
		std_args = []
		for arg in args:
			arg = arg.replace(' ', '\ ')
			std_args.append(arg)
	return std_args

def getSizeInfo(size_text):
	size_line = size_text.split('\n')[-2].strip()
	info_list = re.findall(r'\S+', size_line)
	text_size = int(info_list[0])
	data_size = int(info_list[1])
	bss_size = int(info_list[2])
	flash_size = text_size + data_size
	ram_size = data_size + bss_size
	return (flash_size, ram_size)

def printSizeInfo(size_text, info_dict, language, output_panel):
	(flash_size, ram_size) = getSizeInfo(size_text)
	
	upload_maximum_size_text = info_dict['upload.maximum_size']
	flash_size_text = str(flash_size)
	upload_maximum_size = float(upload_maximum_size_text)
	flash_size_percentage = (flash_size / upload_maximum_size) * 100
	flash_size_text = formatNumber(flash_size_text)
	upload_maximum_size_text = formatNumber(upload_maximum_size_text)
	display_text = 'Binary sketch size: {1} bytes (of a {2} byte maximum, {3}%).\n'
	msg = language.translate(display_text)
	msg = msg.replace('{1}', flash_size_text)
	msg = msg.replace('{2}', upload_maximum_size_text)
	msg = msg.replace('{3}', '%.2f' % flash_size_percentage)
	output_panel.addText(msg)

	upload_maximum_ram_size_text = info_dict['upload.maximum_ram_size']
	if upload_maximum_ram_size_text:
		ram_size_text = str(ram_size)
		upload_maximum_ram_size = float(upload_maximum_ram_size_text)
		ram_size_percentage = (ram_size / upload_maximum_ram_size) * 100
		ram_size_text = formatNumber(ram_size_text)
		upload_maximum_ram_size_text = formatNumber(upload_maximum_ram_size_text)
		display_text = 'Estimated memory use: {1} bytes (of a {2} byte maximum, {3}%).\n'
		msg = msg = language.translate(display_text)
		msg = msg.replace('{1}', ram_size_text)
		msg = msg.replace('{2}', upload_maximum_ram_size_text)
		msg = msg.replace('{3}', '%.2f' % ram_size_percentage)
		output_panel.addText(msg)

def runCommand(command, isSizeCommand, info_dict, language, output_panel, verbose_output):
	args = genCommandArgs(command)
	compilation_process = subprocess.Popen(args, stdout = subprocess.PIPE, \
		stderr = subprocess.PIPE, shell = True)
	result = compilation_process.communicate()
	return_code = compilation_process.returncode
	stdout = result[0]
	stderr = result[1]
				
	if verbose_output:
		output_panel.addText(command)
		output_panel.addText('\n')
		if stdout:
			output_panel.addText(stdout.decode(const.sys_encoding, 'replace'))

	if isSizeCommand:
		size_text = stdout
		printSizeInfo(size_text, info_dict, language, output_panel)

	if stderr:
		output_panel.addText(stderr.decode(const.sys_encoding, 'replace'))
	return return_code

def getNewSerialPort(serial_port, serial_port_list):
	ser = serial.Serial()
	ser.port = serial_port
	ser.baudrate = 1200
	ser.open()
	time.sleep(0.5)
	ser.close()

	serial_port_list.remove(serial_port)
	new_serial_port_list = smonitor.genSerialPortList()
	for serial_port in serial_port_list:
		new_serial_port_list.remove(serial_port)
	while not new_serial_port_list:
		time.sleep(0.5)
		new_serial_port_list = smonitor.genSerialPortList()
		for serial_port in serial_port_list:
			new_serial_port_list.remove(serial_port)
	new_serial_port = new_serial_port_list[0]
	return new_serial_port

class Compilation:
	def __init__(self, language, arduino_info, menu, file_path, is_run_cmd = True):
		self.language = language
		self.arduino_info = arduino_info
		self.menu = menu
		self.is_run_cmd = is_run_cmd
		self.sketch_folder_path = src.getSketchFolderPath(file_path)
		self.sketch_name = src.getSketchNameFromFolder(self.sketch_folder_path)
		now_time = datetime.datetime.now()
		time_str = str(now_time.microsecond)
		compilation_name = 'Compilation_' + self.sketch_name + '_' + time_str
		self.output_panel = stpanel.STPanel(compilation_name)
		self.output_panel.toggleWordWrap()
		self.error_code = 0
		self.is_finished = False

		self.platform = const.settings.get('platform')
		self.board = const.settings.get('board')
		self.programmer = const.settings.get('programmer')

		self.cores_path = self.arduino_info.getCoresPath(self.platform)
		self.core_root = os.path.split(self.cores_path)[0]
		self.platform_file_path = os.path.join(self.core_root, 'platform.txt')
		if not os.path.isfile(self.platform_file_path):
			self.platform_file_path = getPlatformFilePath(self.platform, self.board)

		self.board_type_list = self.arduino_info.getBoardTypeList(self.platform, self.board)
		self.board_type_value_dict = {}
		for board_type in self.board_type_list:
			board_type_caption = self.arduino_info.getPlatformTypeCaption(self.platform, board_type)
			self.board_type_value_dict[board_type] = const.settings.get(board_type_caption)

		self.full_compilation = const.settings.get('full_compilation')
		self.verbose_compilation = const.settings.get('verbose_compilation')
		self.verbose_upload = const.settings.get('verbose_upload')
		self.verify_code = const.settings.get('verify_code')

		self.extra_compilation_flags = const.settings.get('extra_flags', '')
		self.arduino_root = self.arduino_info.getArduinoRoot()
		self.sketchbook_root = const.settings.get('sketchbook_root')
		serial_port = const.settings.get('serial_port')
		self.variant_path = os.path.join(self.core_root, 'variants')
		self.variant_folder_path = self.variant_path
		build_system_path = os.path.join(self.core_root, 'system')
		arduino_version = self.arduino_info.getVersion()
		self.archive_file = 'core.a'
		self.hex_file_path = ''
		
		self.cores_path = self.cores_path.replace(os.path.sep, '/')
		self.core_root = self.core_root.replace(os.path.sep, '/')
		self.arduino_root = self.arduino_root.replace(os.path.sep, '/')

		self.base_info_dict = {}
		self.base_info_dict['runtime.ide.path'] = self.arduino_root
		self.base_info_dict['build.project_name'] = self.sketch_name
		self.base_info_dict['serial.port'] = serial_port
		self.base_info_dict['serial.port.file'] = serial_port
		self.base_info_dict['archive_file'] = self.archive_file
		self.base_info_dict['build.system.path'] = build_system_path
		self.base_info_dict['software'] = 'ARDUINO'
		self.base_info_dict['runtime.ide.version'] = '%d' % arduino_version
		self.base_info_dict['source_file'] = '{source_file}'
		self.base_info_dict['object_file'] = '{object_file}'
		self.base_info_dict['object_files'] = '{object_files}'
		self.base_info_dict['includes'] = '{includes}'

	def isReady(self):
		state = False
		self.error_code = 1
		if self.platform_file_path:
			state = True
			self.error_code = 0
		return state

	def start(self):
		if self.isReady:
			self.output_panel.clear()
			self.starttime = datetime.datetime.now()
			compilation_thread = threading.Thread(target=self.compile)
			compilation_thread.start()
		else:
			self.error_code = 1
			self.is_finished = True

	def compile(self):
		self.postCompilationProcess()
		if self.is_run_cmd:
			display_text = 'Start compilation...\n'
			msg = self.language.translate(display_text)
			self.output_panel.addText(msg)
			self.runCompile()
		self.is_finished = True

	def postCompilationProcess(self):
		display_text = 'Gathering compilation infomation...\n'
		msg = self.language.translate(display_text)
		self.output_panel.addText(msg)
		(main_src_number, self.main_src_path) = self.genMainSrcFileInfo()
		if main_src_number == 0:
			self.error_code = 2
			display_text = 'Error: No main source file was found. A main source file should contain setup() and loop() functions.\n'
			msg = self.language.translate(display_text)
			self.output_panel.addText(msg)
			self.is_finished = True
		elif main_src_number > 1:
			self.error_code = 3
			display_text = 'Error: More than one ({1}) main source files were found. A main source file contains setup() and loop() functions.\n'
			msg = self.language.translate(display_text)
			msg = msg.replace('{1}', '%d' % main_src_number)
			self.output_panel.addText(msg)
			self.is_finished = True
		else:
			self.checkBuildPath()
			self.info_dict = self.genInfoDict()
			self.core_src_path_list = self.genCoreSrcPathList()
			self.completeInfoDict()
			self.genBuildMainSrcFile()
			self.library_src_path_list = self.genLibrarySrcPathList()
			self.genCompilationCommandList()

	def runCompile(self):
		if self.error_code == 0:
			self.cleanObjFiles()
			self.runCompilationCommands()

	def checkBuildPath(self):
		self.build_path = os.path.join(self.sketchbook_root, 'build')
		self.build_path = os.path.join(self.build_path, self.sketch_name)
		self.build_path =self.build_path.replace(os.path.sep, '/')
		self.base_info_dict['build.path'] = self.build_path
		if os.path.isfile(self.build_path):
			os.remove(self.build_path)
		if not os.path.exists(self.build_path):
			os.makedirs(self.build_path)

	def genInfoDict(self):
		(board_info_key_list, board_info_dict) = self.genBoardInfo()
		(programmer_info_key_list, programmer_info_dict) = self.genProgrammerInfo()
		(platform_info_key_list, platform_info_dict) = self.genPlatformInfo()

		info_key_list = board_info_key_list + programmer_info_key_list
		info_dict = self.base_info_dict
		info_dict = dict(info_dict, **board_info_dict)
		info_dict = dict(info_dict, **programmer_info_dict)

		if 'build.vid' in info_key_list:
			if not 'build.extra_flags' in info_key_list:
				info_key_list.append('build.extra_flags')
				info_dict['build.extra_flags'] = '-DUSB_VID={build.vid} -DUSB_PID={build.pid}'
		
		for info_key in platform_info_key_list:
			if info_key in info_key_list:
				if not info_dict[info_key]:
					info_dict[info_key] = platform_info_dict[info_key]
			else:
				info_key_list.append(info_key)
				info_dict[info_key] = platform_info_dict[info_key]

		info_dict['compiler.c.flags'] += ' '
		info_dict['compiler.c.flags'] += self.extra_compilation_flags
		info_dict['compiler.cpp.flags'] += ' '
		info_dict['compiler.cpp.flags'] += self.extra_compilation_flags

		info_dict['compiler.ino.flags'] = info_dict['compiler.cpp.flags'] + ' -x c++'
		info_dict['recipe.ino.o.pattern'] = info_dict['recipe.cpp.o.pattern'].replace('compiler.cpp.flags', 'compiler.ino.flags')
		info_key_list.append('compiler.ino.flags')
		info_key_list.append('recipe.ino.o.pattern')

		if 'build.variant' in info_dict:
			variant_folder = info_dict['build.variant']
			variant_folder_path = os.path.join(self.variant_path, variant_folder)
			self.variant_folder_path = variant_folder_path.replace(os.path.sep, '/')
			info_dict['build.variant.path'] = self.variant_folder_path
		else:
			core_folder = info_dict['build.core']
			core_folder_path = os.path.join(self.cores_path, core_folder)
			core_folder_path = core_folder_path.replace(os.path.sep, '/')
			info_dict['build.variant.path'] = core_folder_path

		if not 'compiler.path' in info_dict:
			compiler_path = os.path.join(self.arduino_root, 'hardware/tools/avr/bin/')
			compiler_path = compiler_path.replace(os.path.sep, '/')
			info_dict['compiler.path'] = compiler_path

		if 'teensy' in self.platform:
			if 'build.elide_constructors' in info_dict:
				if info_dict['build.elide_constructors'] == 'true':
					info_dict['build.elide_constructors'] = '-felide-constructors'
				else:
					info_dict['build.elide_constructors'] = ''
			if 'build.cpu' in info_dict:
				info_dict['build.mcu'] = info_dict['build.cpu']
			if 'build.gnu0x' in info_dict:
				if info_dict['build.gnu0x'] == 'true':
					info_dict['build.gnu0x'] = '-std=gnu++0x'
				else:
					info_dict['build.gnu0x'] = ''
			if 'build.cpp0x' in info_dict:
				if info_dict['build.cpp0x'] == 'true':
					info_dict['build.cpp0x'] = '-std=c++0x'
				else:
					info_dict['build.cpp0x'] = ''

		if not 'upload.maximum_ram_size' in info_dict:
			if info_dict['build.mcu'] in ram_size_dict:
				info_dict['upload.maximum_ram_size'] = ram_size_dict[info_dict['build.mcu']]
			else:
				info_dict['upload.maximum_ram_size'] = ''

		if 'cmd.path.linux' in info_dict:
			if const.sys_platform == 'linux':
				info_dict['cmd.path'] = info_dict['cmd.path.linux']
				info_dict['config.path'] = info_dict['config.path.linux']

		if not self.verbose_upload:
			if 'upload.quiet' in info_dict:
				info_dict['upload.verbose'] = info_dict['upload.quiet']
			if 'program.quiet' in info_dict:
				info_dict['program.verbose'] = info_dict['program.quiet']
			if 'erase.quiet' in info_dict:
				info_dict['erase.verbose'] = info_dict['erase.quiet']
			if 'bootloader.quiet' in info_dict:
				info_dict['bootloader.verbose'] = info_dict['bootloader.quiet']

		if 'AVR' in self.platform:
			if not self.verify_code:
				if 'upload.quiet' in info_dict:
					info_dict['upload.verbose'] += ' -V'
				if 'program.quiet' in info_dict:
					info_dict['program.verbose'] += ' -V'
				if 'erase.quiet' in info_dict:
					info_dict['erase.verbose'] += ' -V'
				if 'bootloader.quiet' in info_dict:
					info_dict['bootloader.verbose'] += ' -V'

		info_dict = regulariseDictValue(info_dict, info_key_list)
		return info_dict

	def genBoardInfo(self):
		board_file_path = self.arduino_info.getBoardFile(self.platform, self.board)
		(board_info_key_list, board_info_dict) = parseBoradInfo(board_file_path, self.board, self.board_type_value_dict)
		return (board_info_key_list, board_info_dict)
		
	def genProgrammerInfo(self):
		programmer_file_path = self.arduino_info.getProgrammerFile(self.platform, self.programmer)
		(programmer_info_key_list, programmer_info_dict) = parseProgrammerInfo(programmer_file_path, self.programmer)
		return (programmer_info_key_list, programmer_info_dict)

	def genPlatformInfo(self):
		(platform_info_key_list, platform_info_dict) = parsePlatformInfo(self.platform_file_path)
		return (platform_info_key_list, platform_info_dict)

	def genSketchSrcPathList(self):
		os.chdir(self.sketch_folder_path)
		sketch_src_path_list = findSrcFiles('.')
		return sketch_src_path_list

	def genCoreSrcPathList(self):
		core_folder = self.info_dict['build.core']
		self.core_folder_path = os.path.join(self.cores_path, core_folder)
		self.core_folder_path = self.core_folder_path.replace(os.path.sep, '/')
		core_src_path_list = findSrcFiles(self.core_folder_path)
		return core_src_path_list

	def genMainSrcFileInfo(self):
		self.sketch_src_path_list = self.genSketchSrcPathList()
		os.chdir(self.sketch_folder_path)
		(main_src_number, main_src_path) = findMainSrcFile(self.sketch_src_path_list)
		return (main_src_number, main_src_path)

	def genHeaderList(self):
		src_header_list = []
		os.chdir(self.sketch_folder_path)
		for sketch_src_path in self.sketch_src_path_list:
			src_text = osfile.readFileText(sketch_src_path)
			header_list = src.genHeaderListFromSketchText(src_text)
			src_header_list += header_list
		src_header_list = utils.removeRepeatItemFromList(src_header_list)
		self.src_header_list = src_header_list

	def genIncludeLibraryPath(self):
		self.genHeaderList()

		include_library_path_list = ['.', self.core_folder_path]
		if 'build.variant' in self.info_dict:
			include_library_path_list.append(self.variant_folder_path)

		lib_path_list = []
		library_path_list = self.arduino_info.getLibraryPathList(self.platform)
		for library_path in library_path_list:
			header_list_from_library = src.getHeaderListFromFolder(library_path)
			for header in header_list_from_library:
				if header in self.src_header_list:
					library_path = library_path.replace(os.path.sep, '/')
					lib_path_list.append(library_path)
					break
		self.lib_path_list = lib_path_list
		self.include_library_path_list = include_library_path_list + lib_path_list

	def genIncludesText(self):
		self.genIncludeLibraryPath()
		includes_text = ''
		for include_library_path in self.include_library_path_list:
			includes_text += '"-I%s" ' % include_library_path
		includes_text = includes_text[:-1]
		self.includes_text = includes_text

	def completeInfoDict(self):
		self.genIncludesText()
		ext_list = ['c', 'cpp', 'ino']
		for ext in ext_list:
			pattern = 'recipe.%s.o.pattern' % ext
			command = self.info_dict[pattern]
			command = command.replace('{includes}', self.includes_text)
			self.info_dict[pattern] = command

	def genBuildMainSrcFile(self):
		filename = os.path.split(self.main_src_path)[1]
		filename += '.cpp'
		self.build_main_src_path = os.path.join(self.build_path, filename)
		self.build_main_src_path = self.build_main_src_path.replace(os.path.sep, '/')
		sketch_text = osfile.readFileText(self.main_src_path)
		simple_sketch_text = src.genSimpleSrcText(sketch_text)
		declaration_list = src.genSrcDeclarationList(simple_sketch_text)
		function_list = src.genSrcFunctionList(simple_sketch_text)
		function_list.remove('void setup ()')
		function_list.remove('void loop ()')
		
		new_declaration_list = []
		for function in function_list:
			if not function in declaration_list:
				if not function in new_declaration_list:
					new_declaration_list.append(function)

		header_text = '#include <Arduino.h>\n'
		for declaration in new_declaration_list:
			header_text += declaration
			header_text += ';\n'

		build_src_text = header_text + sketch_text
		osfile.writeFile(self.build_main_src_path, build_src_text)

		self.sketch_src_path_list.remove(self.main_src_path)
		self.sketch_src_path_list.append(self.build_main_src_path)

	def genLibrarySrcPathList(self):
		library_src_path_list = []
		for lib_path in self.lib_path_list:
			library_src_path_list += findLibrarySrcFiles(lib_path)
		return library_src_path_list

	def genSrcCompilationCommandInfo(self, src_path_list):
		command_list = []
		obj_path_list = []
		for src_path in src_path_list:
			filename = os.path.split(src_path)[1]
			filename += '.o'
			obj_path = os.path.join(self.build_path, filename)
			obj_path = obj_path.replace(os.path.sep, '/')
			obj_path_list.append(obj_path)

			src_ext = os.path.splitext(src_path)[1]
			if src_ext in ['.c', '.cc']:
				pattern = 'recipe.c.o.pattern'
			elif src_ext in ['.cpp', '.cxx']:
				pattern = 'recipe.cpp.o.pattern'
			elif src_ext in ['.ino', '.pde']:
				pattern = 'recipe.ino.o.pattern'
			command_text = self.info_dict[pattern]
			command_text = command_text.replace('{source_file}', src_path)
			command_text = command_text.replace('{object_file}', obj_path)
			command_list.append(command_text)
		return (obj_path_list, command_list)

	def genArCommandInfo(self, core_obj_path_list):
		command_list = []
		ar_file_path = self.build_path + '/' + self.archive_file
		ar_file_path_list = [ar_file_path]

		object_files = ''
		for sketch_obj_path in core_obj_path_list:
			object_files += '"%s" ' % sketch_obj_path
		object_files = object_files[:-1]

		pattern = 'recipe.ar.pattern'
		command_text = self.info_dict[pattern]
		command_text = command_text.replace('"{object_file}"', object_files)
		command_list.append(command_text)
		return (ar_file_path_list, command_list)

	def genElfCommandInfo(self, sketch_obj_path_list):
		command_list = []
		elf_file_path = self.build_path + '/' + self.sketch_name + '.elf'
		elf_file_path_list = [elf_file_path]

		object_files = ''
		for sketch_obj_path in sketch_obj_path_list:
			object_files += '"%s" ' % sketch_obj_path
		object_files = object_files[:-1]

		pattern = 'recipe.c.combine.pattern'
		command_text = self.info_dict[pattern]
		command_text = command_text.replace('{object_files}', object_files)
		command_list.append(command_text)
		return (elf_file_path_list, command_list)

	def genEepCommandInfo(self):
		command_list = []
		eep_file_path = self.build_path + '/' + self.sketch_name + '.eep'
		eep_file_path_list = [eep_file_path]

		pattern = 'recipe.objcopy.eep.pattern'
		command_text = self.info_dict[pattern]
		command_list.append(command_text)
		return (eep_file_path_list, command_list)

	def genHexCommandInfo(self):
		command_list = []

		pattern = 'recipe.objcopy.hex.pattern'
		command_text = self.info_dict[pattern]
		ext = command_text[-5:-1]
		hex_file_path = self.build_path + '/' + self.sketch_name + ext
		hex_file_path_list = [hex_file_path]

		pattern = 'recipe.objcopy.hex.pattern'
		command_text = self.info_dict[pattern]
		command_list.append(command_text)
		return (hex_file_path_list, command_list)

	def genSizeCommandList(self):
		command_list = []

		pattern = 'recipe.size.pattern'
		command_text = self.info_dict[pattern]
		command_text = command_text.replace('-A', '')
		command_text = command_text.replace('.hex', '.elf')
		command_list.append(command_text)
		return command_list

	def genCompilationCommandList(self):
		(sketch_obj_path_list, sketch_command_list) = self.genSrcCompilationCommandInfo(self.sketch_src_path_list)
		(core_obj_path_list, core_command_list) = self.genSrcCompilationCommandInfo(self.core_src_path_list + self.library_src_path_list)
		(ar_file_path_list, ar_command_list) = self.genArCommandInfo(core_obj_path_list)
		(elf_file_path_list, elf_command_list) = self.genElfCommandInfo(sketch_obj_path_list)
		(eep_file_path_list, eep_command_list) = self.genEepCommandInfo()
		(hex_file_path_list, hex_command_list) = self.genHexCommandInfo()
		size_command_list = self.genSizeCommandList()

		ar_file_path = ar_file_path_list[0]
		if not os.path.isfile(ar_file_path):
			self.full_compilation = True
		self.hex_file_path = hex_file_path_list[0]

		self.created_file_list = []
		self.compilation_command_list = []
		self.created_file_list += sketch_obj_path_list
		self.compilation_command_list += sketch_command_list
		if self.full_compilation:
			self.created_file_list += core_obj_path_list
			self.compilation_command_list += core_command_list
			self.created_file_list += ar_file_path_list
			self.compilation_command_list += ar_command_list
		self.created_file_list += elf_file_path_list
		self.compilation_command_list += elf_command_list
		if self.info_dict['recipe.objcopy.eep.pattern']:
			self.created_file_list += eep_file_path_list
			self.compilation_command_list += eep_command_list
		self.created_file_list += hex_file_path_list
		self.compilation_command_list += hex_command_list
		self.created_file_list += ['size']
		self.compilation_command_list += size_command_list

	def cleanObjFiles(self):
		display_text = 'Cleaning...\n'
		msg = self.language.translate(display_text)
		self.output_panel.addText(msg)
		for file_path in self.created_file_list:
			if os.path.isfile(file_path):
				os.remove(file_path)

	def runCompilationCommands(self):
		termination_with_error = False
		os.chdir(self.sketch_folder_path)
		compilation_info = zip(self.created_file_list, self.compilation_command_list)
		for (created_file, compilation_command) in compilation_info:
			isSizeCommand = False
			if created_file:
				if created_file == 'size':
					isSizeCommand = True
				else:
					display_text = 'Creating {1}...\n'
					msg = self.language.translate(display_text)
					msg = msg.replace('{1}', created_file)
					self.output_panel.addText(msg)
			return_code = runCommand(compilation_command, isSizeCommand, self.info_dict, \
				self.language, self.output_panel, self.verbose_compilation)
			if return_code != 0:
				termination_with_error = True
				break
		
		if termination_with_error:
			self.error_code = 4
			display_text = '[Stino - Compilation terminated with errors.]\n'
			msg = self.language.translate(display_text)
			self.output_panel.addText(msg)
		else:
			self.endtime = datetime.datetime.now()
			interval = (self.endtime - self.starttime).microseconds * 1e-6
			display_text = '[Stino - Compilation completed.]\n'
			msg = self.language.translate(display_text)
			self.output_panel.addText(msg)
			sublime.set_timeout(self.TurnFullCompilationOff, 0)

	def TurnFullCompilationOff(self):
		const.settings.set('full_compilation', False)
		const.save_settings()
		self.menu.commandUpdate()

	def getHexFilePath(self):
		return self.hex_file_path

	def isTerminatedWithError(self):
		if self.error_code == 0:
			state = False
		else:
			state = True
		return state

	def getOutputPanel(self):
		return self.output_panel

	def getInfoDict(self):
		return self.info_dict

class Upload:
	def __init__(self, language, arduino_info, menu, file_path, mode = 'upload', \
		serial_port_in_use_list = None, serial_port_monitor_dict = None):
		self.language = language
		self.cur_compilation = Compilation(language, arduino_info, menu, file_path)
		self.output_panel = self.cur_compilation.getOutputPanel()
		self.error_code = 0
		self.is_finished = False
		self.mode = mode
		self.board = const.settings.get('board')
		self.verbose_upload = const.settings.get('verbose_upload')
		
		self.serial_port_in_use_list = serial_port_in_use_list
		self.serial_port_monitor_dict = serial_port_monitor_dict
		self.serial_port = const.settings.get('serial_port')
		self.serial_port_list = smonitor.genSerialPortList()
		
		self.serial_monitor_is_running = False
		if self.serial_port_in_use_list:
			if self.serial_port in self.serial_port_in_use_list:
				self.serial_monitor = self.serial_port_monitor_dict[self.serial_port]
				self.serial_monitor_is_running = True

	def start(self):
		self.cur_compilation.start()
		upload_thread = threading.Thread(target=self.upload)
		upload_thread.start()

	def upload(self):
		while not self.cur_compilation.is_finished:
			time.sleep(0.5)
		if self.cur_compilation.isTerminatedWithError():
			self.error_code = 1
		else:
			self.info_dict = self.cur_compilation.getInfoDict()
			self.hex_file_path = self.cur_compilation.getHexFilePath()
			display_text = 'Start uploading {1}...\n'
			msg = self.language.translate(display_text)
			msg = msg.replace('{1}', self.hex_file_path)
			self.output_panel.addText(msg)
			if self.mode == 'upload':
				upload_command = self.info_dict['upload.pattern']
				if self.serial_monitor_is_running:
					self.serial_monitor.stop()
					time.sleep(0.1)
				if 'Leonardo' in self.board or 'Micro' in self.board:
					new_serial_port = getNewSerialPort(self.serial_port, self.serial_port_list)
					upload_command = upload_command.replace(self.serial_port, new_serial_port)
					self.serial_port = new_serial_port
			elif self.mode == 'upload_using_programmer':
				if 'program.pattern' in self.info_dict:
					upload_command = self.info_dict['program.pattern']
			else:
				upload_command = ''
			if upload_command:
				termination_with_error = False
				command_list = [upload_command]
				if 'reboot.pattern' in self.info_dict:
					reboot_command = self.info_dict['reboot.pattern']
					command_list.append(reboot_command)
				for command in command_list:
					isSizeCommand = False
					return_code = runCommand(command, isSizeCommand, self.info_dict, \
						self.language, self.output_panel, self.verbose_upload)
					if return_code != 0:
						termination_with_error = True
						break
				if termination_with_error:
					self.error_code = 2
					display_text = '[Stino - Uploading terminated with errors.]\n'
					msg = self.language.translate(display_text)
					self.output_panel.addText(msg)
				else:
					display_text = '[Stino - Uploading completed.]\n'
					msg = self.language.translate(display_text)
					self.output_panel.addText(msg)
				if self.mode == 'upload':
					if self.serial_monitor_is_running:
						self.serial_monitor.setSerialPort(self.serial_port)
						sublime.set_timeout(self.serial_monitor.start, 0)
			else:
				self.error_code = 3
		self.is_finished = True

class BurnBootloader:
	def __init__(self, language, arduino_info, menu, file_path):
		self.language = language
		self.cur_compilation = Compilation(language, arduino_info, menu, file_path, is_run_cmd = False)
		self.output_panel = self.cur_compilation.getOutputPanel()
		self.error_code = 0
		self.is_finished = False
		self.verbose_upload = const.settings.get('verbose_upload')

	def start(self):
		self.cur_compilation.start()
		upload_thread = threading.Thread(target=self.burn)
		upload_thread.start()

	def burn(self):
		while not self.cur_compilation.is_finished:
			time.sleep(0.5)
		if self.cur_compilation.isTerminatedWithError():
			self.error_code = 1
		else:
			self.info_dict = self.cur_compilation.getInfoDict()
			if 'bootloader.file' in self.info_dict:
				display_text = 'Start burning {1}...\n'
				msg = self.language.translate(display_text)
				msg = msg.replace('{1}', self.info_dict['bootloader.file'])
				self.output_panel.addText(msg)
				termination_with_error = False
				erase_command = self.info_dict['erase.pattern']
				burn_command = self.info_dict['bootloader.pattern']
				command_list = [erase_command, burn_command]
				for command in command_list:
					isSizeCommand = False
					return_code = runCommand(command, isSizeCommand, self.info_dict, \
						self.language, self.output_panel, self.verbose_upload)
					if return_code != 0:
						termination_with_error = True
						break
				if termination_with_error:
					self.error_code = 2
					display_text = '[Stino - Bootloader burning terminated with errors.]\n'
					msg = self.language.translate(display_text)
					self.output_panel.addText(msg)
				else:
					display_text = '[Stino - Bootloader burning completed.]\n'
					msg = self.language.translate(display_text)
					self.output_panel.addText(msg)
			else:
				self.error_code = 3
		self.is_finished = True