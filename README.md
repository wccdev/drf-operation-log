# drf-operation-log


[![GitHub license](https://img.shields.io/github/license/anyidea/drf-operation-log)](https://github.com/anyidea/drf-operation-log/blob/master/LICENSE)
[![pypi-version](https://img.shields.io/pypi/v/drf-operation-log.svg)](https://pypi.python.org/pypi/drf-operation-log)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/drf-operation-log)
[![PyPI - DRF Version](https://img.shields.io/badge/djangorestframework-%3E%3D3.0-red)](https://www.django-rest-framework.org)
[![Build Status](https://app.travis-ci.com/aiden520/drfexts.svg?branch=master)](https://app.travis-ci.com/aiden520/drfexts)


## Documentation

## Requirement
* Python 3.8, 3.9, 3.10
* Django 3.2, 4.0, 4.1

## Installation
Install using pip...
```bash
pip install drf-operation-log
```
Add `'drf_operation_log'` to your `INSTALLED_APPS` setting.
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    ...
    'drf_operation_log',
]
```

Let's take a look at a quick start of using drf_operation_log to saving operation logs.

Run the `drf_operation_log` migrations using:
```bash
python manage.py migrate drf_operation_log
```

Add the following to your `settings.py` module:
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    ...
    'drf_operation_log',
]

DRF_OPERATION_LOG_SAVE_DATABASE = True
```
