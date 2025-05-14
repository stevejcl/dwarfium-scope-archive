# dwarfium-scope-archive
A tool to explore your Dwarf Session


Installation

1. Clone this repository 

2. Then Installdependancies  with
  
     python -m pip install -r requirements.txt


Then you can start it with => python .\dwarf_backup_cli.py --gui

You can use python .\dwarf_backup_cli.py to see your achives files associate with the target in the database

the database is a sqlite3, it will be created at startup, the name is dwarf_backup.db

You can analyse your sessions saved on Hard Disk or your current session on the Dwarf connected with USB.

# Dwarfium Scope Archive

Welcome to the Dwarfium Scope Archive project! 
This project is designed to manage and organize astrophotography data from the DWARF telescope system.
It includes tools for handling backups, organizing images, and integrating various devices like USB, FTP, and MTP (DWARF2) for seamless data transfer. 

## Table of Contents

- [Introduction](#chapter-1-introduction)
- [Installation](#chapter-2-installation)
- [Usage](#chapter-3-usage)
- [Features](#chapter-4-features)
- [Upcoming Features](#chapter-5-upcoming-features)
- [Contributing](#chapter-6-contributing)
- [License](#chapter-7-license)

## Chapter 1: Introduction

The Dwarfium Scope Archive is a collection of pages designed to manage backups and organize astrophotography files produced by the Dwarfium telescope. This includes managing FITS files, JPG images, and other related metadata for easy retrieval and processing.

This project is currently under active development, and some features (such as FTP and MTP integrations) are yet to be fully implemented.

## Chapter 2: Installation

To install the Dwarfium Scope Archive, follow these steps:

### Prerequisites

- Python 3.10+
- Required Python Packages:
  You can install the dependencies using:
  ```bash
  pip install -r requirements.txt
   
  ```

### Installation Steps
Clone the repository:

  ```bash
git clone https://github.com/yourusername/dwarfium-scope-archive.git
  ```
  
Install the necessary Python libraries:

  ```bash
pip install -r requirements.txt
  ```

Currently Supported Devices: USB (more details to follow).

## Chapter 3: Usage

Running the Application
To launch the application, run:

  ```bash
python dwarfium_scope_archive.py
  ```

or use the build exe directly on windows

## Chapter 4: Features

### Home Page:

On this page, you will see a slideshow of your favorite images, which you have marked on the Explore Page.

![image](https://github.com/user-attachments/assets/8d4f60fe-27a2-462e-a834-7c98972c011a)

### Dwarf Configuration Page:

Configure your Dwarf device by adding a name, a description, and the USB path when it's plugged into your computer. You can also provide the IP address in STA Mode to connect with FTP.

![image](https://github.com/user-attachments/assets/58704632-0e47-4f06-ba20-37278b679dbe)

For Dwarf 2, it will be detected on your computer through MTP. This will allow you to scan its drive and later add sessions to your backup drive.

Two action buttons allow you to:

Launch a scan of the Dwarf drive.

Launch the Explore path to view what's currently on your Dwarf, including:

Image previews.

Session details (exposure, gain, number of images).

Whether the session is backed up or not.

### Backup Page:

Configure your Backup Drive by adding a name, description, and the main path of the backup drive. Specify a subdirectory within the backup drive where you want to store your Dwarf sessions.

![image](https://github.com/user-attachments/assets/2c73c433-e4fb-40d2-887e-bb748ebe40ef)

A backup drive is associated with a Dwarf device.

You can create multiple levels of directories. For example, you could create a sublevel with object names, and under each object, store its sessions. This way, all your sessions will be organized by object name (directory name) instead of the target present in the session.

Later, a tool will be provided to manage your object list, allowing you to change the object of a session.

Additionally, there will be a section to add Darks sessions, which you can associate with your sessions for processing.

### Explore Page:
This is the main view where you can see your sessions, organized by object, backup, or Dwarf.

![explore](https://github.com/user-attachments/assets/2b46a0eb-c110-4263-a3b7-1572aaab5537)

You will be able to:

View images (JPG, PNG, or even FITS).

Add images to your favorites.

Open images in full screen.

Open the image's directory.

You will also have access to all the session details, such as the number of images, exposure, gain, and more.
You'll also know if the session is stored on your Dwarf or not.

### Chapter 5: Upcoming Features

FTP Support:
Integration with FTP, allowing direct connection to the Dwarf for data retrieval and storage.

MTP Support:
Integration with MTP (Media Transfer Protocol) for Dwarf 2 to analyze the current Dwarf disk.

FITS Updates:
Enhancements and updates to better handle FITS files, including new features and improved processing.

Object Management:
Tools to manage and update the objects (targets) of your astrophotography sessions.

Change Object (Target) of the Session:
Ability to change the object (target) associated with a session, giving more flexibility for reclassification.

Moving Files Between Backup / Object:
Feature to move files between different backups or object directories, enabling better organization.

Add Darks Backup and Association with Dwarf:
Support for managing Darks sessions, including adding and associating them with Dwarf sessions for processing.

Regroup Object Sessions for Mosaic:
The ability to group sessions based on objects, enabling easier management and creation of mosaics.


### Chapter 6: Contributing

We welcome contributions to the Dwarfium Scope Archive! Here’s how you can contribute:

Fork the repository

Create a new branch

Make your changes

Submit a pull request

For bug reports or feature requests, please open an issue.

### Chapter 7: License

This project is licensed under the MIT License

