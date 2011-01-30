# Resources:
# http://pytz.sourceforge.net/
# http://en.wikipedia.org/wiki/List_of_tz_database_time_zones

import argparse, git, os, ConfigParser
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.repositories.models import *
from pytz import timezone, utc

# Command line parser
parser = argparse.ArgumentParser(description='Source Control Correlator')
parser.add_argument("--config", default="postgres.ini")
args = parser.parse_args()

# Config parsing
config = ConfigParser.RawConfigParser()
config.read(args.config)
repository = git.Repo(config.get('repository', 'directory'))
repository_pk = config.getint('repository', 'id')

# Timezone information
tzs = {}
tzs['proff@suburbia.net'] = 'Australia/Melbourne'
tzs['bryanh@giraffe.netgate.net'] = 'America/Los_Angeles'
tzs['E.Mergl@bawue.de'] = 'Europe/Berlin'
tzs['byronn@insightdist.com'] = 'America/New_York'
tzs['peter@retep.org.uk'] = 'Europe/London'
tzs['vadim4o@yahoo.com'] = 'America/Los_Angeles'
tzs['vev@michvhf.com'] = 'America/Detroit'
tzs['pjw@rhyme.com.au'] = 'Australia/Melbourne'
tzs['lockhart@fourpalms.org'] = 'America/Los_Angeles'
tzs['inoue@tpf.co.jp'] = 'Asia/Tokyo'
tzs['barry@xythos.com'] = 'America/Los_Angeles'
tzs['davec@fastcrypt.com'] = 'America/Toronto'
tzs['books@ejurka.com'] = 'America/Los_Angeles'
tzs['db@zigo.dhs.org'] = 'Europe/London'
tzs['webmaster@postgresql.org'] = 'UTC'
tzs['JanWieck@Yahoo.com'] = 'America/New_York'
tzs['darcy@druid.net'] = 'America/Toronto'
tzs['stark@mit.edu'] = 'Europe/Dublin'
tzs['teodor@sigaev.ru'] = 'Europe/Moscow'
tzs['ishii@postgresql.org'] = 'Asia/Tokyo'
tzs['scrappy@hub.org'] = 'America/Halifax'
tzs['mail@joeconway.com'] = 'America/Los_Angeles'
tzs['simon@2ndQuadrant.com'] = 'Europe/London'
tzs['itagaki.takahiro@gmail.com'] = 'Asia/Tokyo'
tzs['meskes@postgresql.org'] = 'Europe/Berlin'
tzs['alvherre@alvh.no-ip.org'] = 'America/Santiago'
tzs['andrew@dunslane.net'] = 'America/New_York'
tzs['tgl@sss.pgh.pa.us'] = 'America/New_York'
tzs['magnus@hagander.net'] = 'Europe/Stockholm'
tzs['heikki.linnakangas@iki.fi'] = 'Europe/Helsinki'
tzs['rhaas@postgresql.org'] = 'America/New_York'
tzs['peter_e@gmx.net'] = 'Europe/Helsinki'
tzs['bruce@momjian.us'] = 'America/New_York'

for c in Commit.objects.filter(author__repository__pk=repository_pk):
    # Check if there's possibly no timezone information
    if c.local_time == c.utc_time:
        # Get the timezone
        try:
            tz = timezone(tzs[c.author.email])
        except KeyError:
            # Handle the special cases
            if c.author.email == 'neilc@samurai.com':
                if c.utc_time.year <= 2007:
                    tz = timezone('America/Toronto')
                else:
                    tz = timezone('America/Los_Angeles')
            else:
                raise KeyError

        # Modify and save
        c.local_time = c.local_time.replace(tzinfo=utc).astimezone(tz).replace(tzinfo=None)
        c.save()
