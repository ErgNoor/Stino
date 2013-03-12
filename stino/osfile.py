#-*- coding: utf-8 -*-
# stino/osfile.py

import sublime
import os

from stino import utils
from stino import const

def getWinVolumeList():
	vol_list = []
	for label in xrange(67, 90):
		vol = chr(label) + ':\\'
		if os.path.isdir(vol):
			vol_list.append(vol)
	return vol_list

def getAppRootList():
	app_root_list = []
	if const.sys_platform == 'windows':
		app_root_list = getWinVolumeList()
	elif const.sys_platform == 'linux':
		home_root = os.getenv('HOME')
		app_root_list = [home_root, '/usr', '/opt']
	elif const.sys_platform == 'osx':
		home_root = os.getenv('HOME')
		app_root_list = ['/Applications', home_root]
	return app_root_list

def getHomeRootList():
	if const.sys_platform == 'windows':
		home_root_list = getWinVolumeList()
	else:
		home_root = os.getenv('HOME')
		home_root_list = [home_root]
	return home_root_list

def isDirAccess(dir_path):
	state = False
	try:
		os.listdir(dir_path)
	except OSError:
		state = False
	else:
		state = True
	return state

def isFileAccess(file_path):
	state = False
	try:
		opened_file = open(file_path)
	except IOError:
		state = False
	else:
		opened_file.close()
		state = True	
	return state

def listDir(path, with_dirs = True, with_files = True):
	file_list = []
	path = utils.convertAsciiToUtf8(path)
	if os.path.isdir(path):
		org_file_list = os.listdir(path)
		for cur_file in org_file_list:
			if cur_file[0] == '$' or cur_file[0] == '.':
				continue
			cur_file = utils.convertAsciiToUtf8(cur_file)
			cur_file_path = os.path.join(path, cur_file)
			if os.path.isdir(cur_file_path):
				if with_dirs:
					if isDirAccess(cur_file_path):
						file_list.append(cur_file)
			else:
				if with_files:
					if isFileAccess(cur_file_path):
						file_list.append(cur_file)
	return file_list

def readFileText(file_path):
	text = ''
	if isFileAccess(file_path):
		opened_file = open(file_path)
		lines = opened_file.readlines()
		opened_file.close()

		for line in lines:
			line = utils.convertAsciiToUtf8(line)
			text += line
	return text

def readFileLines(file_path):
	text = readFileText(file_path)
	lines = utils.convertTextToLines(text)
	return lines

def writeFile(file_path, text, encoding = 'utf-8'):
	text = text.encode(encoding)
	f = open(file_path, 'w')
	f.write(text)
	f.close()

def getRealPath(path):
	if const.sys_platform == 'osx':
		path = os.path.join(path, 'Contents/Resources/JAVA')
	return path

def openUrl(url):
	arduino_root = const.settings.get('arduino_root')
	arduino_root = getRealPath(arduino_root)
	reference_path = os.path.join(arduino_root, 'reference')
	reference_path = reference_path.replace(os.path.sep, '/')
	ref_file = '%s/%s.html' % (reference_path, url)
	sublime.run_command('open_url', {'url': ref_file})

def genFileListFromPathList(path_list):
	file_list = []
	for cur_path in path_list:
		if cur_path == 'Button':
			file_list.append('Select Current Folder')
		else:
			cur_file = os.path.split(cur_path)[1]
			if cur_file:
				file_list.append(cur_file)
			else:
				file_list.append(cur_path)
	return file_list

def genSubPathList(path, with_files = True, with_parent = True, with_button = False):
	path = os.path.normpath(path)
	file_list = listDir(path, with_files = with_files)
	if with_parent:
		file_list.insert(0, '..')
	path_list = [os.path.join(path, cur_file) for cur_file in file_list]
	if with_button:
		path_list.insert(0, 'Button')
	return path_list

def enterSubDir(top_path_list, level, index, sel_path, with_files = True, with_parent = True, with_button = False):
	cur_dir = os.path.split(sel_path)[1]
	if level > 0:
		if cur_dir == '..':
			level -= 1
		else:
			level += 1
	else:
		level += 1

	if level == 0:
		path_list = top_path_list
	else:
		path_list = genSubPathList(sel_path, with_files, with_parent, with_button)

	return (level, path_list)