#!/usr/bin/env python
import os
import sys
import env

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instagram_notifier.settings')
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()