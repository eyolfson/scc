Source Control Correlator
=========================

http://www.eyolfson.com/scc/

Software Used
-------------
argparse 1.1
Django 1.2.5
GitPython 0.3.1-beta2
PyTZ 2011b
PostgreSQL 8.4

Database
--------
There are two options in order to reconstruct the databse.

1. Use the provided tables.sql file. This contains tables for linux and
postgresql. I created the table dump by running the command 
`pg_dump -t 'scc_*' -f tables.sql --no-owner scc`.

2. Create your own database, define it in `scc_website/settings_local.py` and
run `scc_website/manage.py syncdb` to create all the tables for you. You can
then use `populate_tables.py`. Some code repositories, such as the Linux kernel,
use a specific encoding. For example, I used the command `python2 populate_tables.py
linux $HOME/workspace/linux iso-8859-2`.
