import numpy, os, sys

# Set the path
path = '/home/jon/git/scc-web'
if path not in sys.path:
    sys.path.append(path)
path = '/home/jon/git/scc-web/scc_website'
if path not in sys.path:
    sys.path.append(path)
del path

# Import the Django models
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.scc import models


# r = Repository.objects.get(pk=1)
# exclude_pk = 222332
# xp_cutoff = 2000
# file_prefix = 'linux-'

r = models.Repository.objects.get(slug='xorg')

xp_cutoff = 4320
file_prefix = 'xorg-'

experiences = ["%d" % i for i in range(120, xp_cutoff+120, 120)]
count = [0 for i in range(len(experiences))]

bug_lifetimes = []
for b in models.FixingCommit.objects.filter(commit__repository=r):
    fix_time = b.commit.utc_time
    # if not fix_time.year in years:
    #     years[fix_time.year] = []
    introduction_times = []
    for c in b.introducing_commits.all():
        # if c.pk == exclude_pk:
        #     continue
        introduction_times.append((c.utc_time, c.sha1))
    if len(introduction_times) == 0:
        continue
    introduction_times.sort()
    days = (fix_time - introduction_times[0][0]).days
    if days >= 0 and days < xp_cutoff:
        count[days/120] += 1
        bug_lifetimes.append(days)
        # if days > 5000:
        #     print introduction_times[0][1], "to", b.fix_commits.all()[0].sha1


import csv
writer = csv.writer(open('%sbug-lifetime.csv' % file_prefix, 'wb'))
for i in range(len(count)):
    writer.writerow([experiences[i], count[i]])

# # for k in years.iterkeys():
# #     print k
# #     print numpy.average(years[k])
# #     print numpy.average(years[k])

print numpy.average(bug_lifetimes)
print numpy.std(bug_lifetimes)
