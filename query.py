import csv, os
from datetime import datetime
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.repositories.models import *

r = Repository.objects.get(pk=1)
exclude_pk = 222332
xp_cutoff = 2000
file_prefix = 'linux-'

# r = Repository.objects.get(pk=4)
# exclude_pk = 532279
# xp_cutoff = 5300
# file_prefix = 'postgresql-'

ci_set = CommitInformation.objects.filter(commit__author__repository=r).exclude(commit__pk=exclude_pk)

days = ['Mon', 'Tues', 'Wed', 'Thur', 'Fri', 'Sat', 'Sun']
classes = ['Job', 'Daily', 'Weekly', 'Monthly', 'Other', 'Single']
hours = range(24)
experiences = ["<%d" % i for i in range(120, xp_cutoff+120, 120)]

def div(x, y):
    return float(x)/float(y)

class DataCollector():

    AVERAGE_ROW = 'Average'
    OVERALL_CATEGORY = 'Overall'
    
    def __init__(self, variables, calculation, rows, categories=[]):
        self._variable_map = {}
        for i in xrange(len(variables)):
            self._variable_map[variables[i]] = i

        self._calculation = calculation

        self._row_map = {}
        for i in xrange(len(rows)):
            self._row_map[rows[i]] = i

        self._category_map = {}
        i = 0
        for category in categories:
            self._category_map[category] = i
            i += 1
        self._category_map[DataCollector.OVERALL_CATEGORY] = i

        self._data = [[0 for j in xrange(len(self._variable_map)*len(self._category_map))] for i in xrange(len(self._row_map)+1)]

    def update(self, variable, row, category=None, amount=1):
        if category is None:
            category = DataCollector.OVERALL_CATEGORY

        if not isinstance(row, int):
            row = self._row_map[row]
        if not isinstance(category, int):
            category = self._category_map[category]

        i = row
        j = len(self._variable_map)*category+self._variable_map[variable]

        self._data[i][j] += amount
        self._data[len(self._row_map)][j] += amount

        if category is not self._category_map[DataCollector.OVERALL_CATEGORY]:
            j = len(self._variable_map)*self._category_map[DataCollector.OVERALL_CATEGORY]+self._variable_map[variable]
            self._data[i][j] += amount
            self._data[len(self._row_map)][j] += amount

    def write_csv(self, filename):
        # Open the file and write the header
        import csv
        writer = csv.writer(open('data.csv', 'wb'))
        writer.writerows(self._data)
        
        writer = csv.writer(open('%s.csv' % filename, 'wb'))
        header = ['' for i in xrange(len(self._category_map)+1)]
        for item in self._category_map.iteritems():
            header[item[1]+1] = item[0]
        writer.writerow(header)

        # Create the calculation string to be eval'ed
        substitute = 'self._data[i][%d*j+%%d]' % len(self._variable_map)
        calculation = self._calculation
        for item in self._variable_map.iteritems():
            calculation = calculation.replace(item[0], substitute % item[1])

        # Create the rows
        rows = [['' for j in xrange(len(self._category_map)+1)] for i in xrange(len(self._row_map)+1)]
        for item in self._row_map.iteritems():
            rows[item[1]][0] = item[0]
        rows[len(self._row_map)][0] = DataCollector.AVERAGE_ROW

        # Do the calculations
        for i in xrange(len(self._row_map)+1):
            for j in xrange(len(self._category_map)):
                try:
                    rows[i][j+1] = eval(calculation)
                except ZeroDivisionError:
                    rows[i][j+1] = 0
        writer.writerows(rows)

# # Commits per Day
# commits_day_dc = DataCollector(['total_commits'],
#                                  'total_commits',
#                                  days,
#                                  classes)
# for ci in ci_set:
#     i = ci.commit.local_time.weekday()
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     commits_day_dc.update('total_commits', i, j)
# commits_day_dc.write_csv('%scommits-day' % file_prefix)

# # Bugginess per Day
# bugginess_day_dc = DataCollector(['buggy_commits', 'total_commits'],
#                                  '100*div(buggy_commits, total_commits)',
#                                  days,
#                                  classes)
# for ci in ci_set:
#     i = ci.commit.local_time.weekday()
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         bugginess_day_dc.update('buggy_commits', i, j)
#     bugginess_day_dc.update('total_commits', i, j)
# bugginess_day_dc.write_csv('bugginess-day')

# # Introductions per Day
# introductions_day_dc = DataCollector(['introduction_commits', 'total_commits'],
#                                  'div(introduction_commits, total_commits)',
#                                  days,
#                                  classes)
# for ci in ci_set:
#     i = ci.commit.local_time.weekday()
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         introductions_day_dc.update('introduction_commits', i, j, ci.introduction_count)
#     introductions_day_dc.update('total_commits', i, j)
# introductions_day_dc.write_csv('introductions-day')

# # Severity per Day
# severity_day_dc = DataCollector(['introduction_count', 'lines_changed'],
#                                  'div(introduction_count, lines_changed)',
#                                  days,
#                                  classes)
# for ci in ci_set:
#     i = ci.commit.local_time.weekday()
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         severity_day_dc.update('introduction_count', i, j, ci.introduction_count)
#     severity_day_dc.update('lines_changed', i, j, ci.lines_changed)
# severity_day_dc.write_csv('severity-day')

# Commits per Hour
commits_day_dc = DataCollector(['total_commits'],
                                 'total_commits',
                                 hours,
                                 classes)
for ci in ci_set:
    i = ci.commit.local_time.hour
    classification = ci.commit.author.authorinformation.classification
    day_job = ci.commit.author.authorinformation.day_job
    if day_job:
        j = 0
    elif classification == 'D':
        j = 1
    elif classification == 'W':
        j = 2
    elif classification == 'M':
        j = 3
    elif classification == 'O':
        j = 4
    elif classification == 'S':
        j = 5
    else:
        raise ValueError
    commits_day_dc.update('total_commits', i, j)
commits_day_dc.write_csv('%scommits-hour' % file_prefix)

# # Bugginess per Hour
# bugginess_hour_dc = DataCollector(['buggy_commits', 'total_commits'],
#                                   '100*div(buggy_commits, total_commits)',
#                                   hours,
#                                   classes)
# for ci in ci_set:
#     i = ci.commit.local_time.hour
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         bugginess_hour_dc.update('buggy_commits', i, j)
#     bugginess_hour_dc.update('total_commits', i, j)
# bugginess_hour_dc.write_csv('bugginess-hour')

# # Introductions per Hour
# introductions_hour_dc = DataCollector(['introduction_commits', 'total_commits'],
#                                  'div(introduction_commits, total_commits)',
#                                  hours,
#                                  classes)
# for ci in ci_set:
#     i = ci.commit.local_time.hour
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         introductions_hour_dc.update('introduction_commits', i, j, ci.introduction_count)
#     introductions_hour_dc.update('total_commits', i, j)
# introductions_hour_dc.write_csv('introductions-hour')

# # Severity per Hour
# severity_hour_dc = DataCollector(['introduction_count', 'lines_changed'],
#                                  'div(introduction_count, lines_changed)',
#                                  hours,
#                                  classes)
# for ci in ci_set:
#     i = ci.commit.local_time.hour
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if not ci.merge:
#         if ci.introduction_count > 0:
#             severity_hour_dc.update('introduction_count', i, j, ci.introduction_count)
#         severity_hour_dc.update('lines_changed', i, j, ci.lines_changed)
# severity_hour_dc.write_csv('severity-hour')

# # Commits per Author
# authors = ["%s <%s>" % (a.name, a.email) for a in Author.objects.filter(repository=r)]
# commits_author_dc = DataCollector(['total_commits'],
#                                   'total_commits',
#                                   authors,
#                                   hours)
# for ci in ci_set:
#     i = "%s <%s>" % (ci.commit.author.name, ci.commit.author.email)
#     j = ci.commit.local_time.hour
#     commits_author_dc.update('total_commits', i, j)
# commits_author_dc.write_csv('commits-author')

# # Bugginess per Author
# authors = ["%s <%s>" % (a.name, a.email) for a in Author.objects.filter(repository=r)]
# bugginess_author_dc = DataCollector(['buggy_commits', 'total_commits'],
#                                   '100*div(buggy_commits, total_commits)',
#                                   authors,
#                                   hours)
# for ci in ci_set:
#     i = "%s <%s>" % (ci.commit.author.name, ci.commit.author.email)
#     j = ci.commit.local_time.hour
#     if ci.introduction_count > 0:
#         bugginess_author_dc.update('buggy_commits', i, j)
#     bugginess_author_dc.update('total_commits', i, j)
# bugginess_author_dc.write_csv('bugginess-author')

# # Bugginess per Experience
# authors = {}
# for ci in ci_set:
#     email = ci.commit.author.email
#     if not email in authors:
#         authors[email] = ci.commit.utc_time
#     else:
#         if ci.commit.utc_time < authors[email]:
#             authors[email] = ci.commit.utc_time
# bugginess_experience_dc = DataCollector(['buggy_commits', 'total_commits'],
#                                  '100*div(buggy_commits, total_commits)',
#                                  experiences,
#                                  classes)
# for ci in ci_set:
#     experience = (ci.commit.utc_time - authors[ci.commit.author.email]).days
#     if experience < 0 or experience > xp_cutoff:
#         continue
#     i = experience/120
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         bugginess_experience_dc.update('buggy_commits', i, j)
#     bugginess_experience_dc.update('total_commits', i, j)
# bugginess_experience_dc.write_csv('bugginess-experience')

# # Introductions per Experience
# authors = {}
# for ci in ci_set:
#     email = ci.commit.author.email
#     if not email in authors:
#         authors[email] = ci.commit.utc_time
#     else:
#         if ci.commit.utc_time < authors[email]:
#             authors[email] = ci.commit.utc_time
# introductions_experience_dc = DataCollector(['introduction_commits', 'total_commits'],
#                                             'div(introduction_commits, total_commits)',
#                                             experiences,
#                                             classes)
# for ci in ci_set:
#     experience = (ci.commit.utc_time - authors[ci.commit.author.email]).days
#     if experience < 0 or experience > xp_cutoff:
#         continue
#     i = experience/120
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         introductions_experience_dc.update('introduction_commits', i, j, ci.introduction_count)
#     introductions_experience_dc.update('total_commits', i, j)
# introductions_experience_dc.write_csv('introductions-experience')

# # Severity per Experience
# authors = {}
# for ci in ci_set:
#     email = ci.commit.author.email
#     if not email in authors:
#         authors[email] = ci.commit.utc_time
#     else:
#         if ci.commit.utc_time < authors[email]:
#             authors[email] = ci.commit.utc_time
# severity_experience_dc = DataCollector(['introduction_count', 'lines_changed'],
#                                        'div(introduction_count, lines_changed)',
#                                        experiences,
#                                        classes)
# for ci in ci_set:
#     experience = (ci.commit.utc_time - authors[ci.commit.author.email]).days
#     if experience < 0 or experience > xp_cutoff:
#         continue
#     i = experience/120
#     classification = ci.commit.author.authorinformation.classification
#     day_job = ci.commit.author.authorinformation.day_job
#     if day_job:
#         j = 0
#     elif classification == 'D':
#         j = 1
#     elif classification == 'W':
#         j = 2
#     elif classification == 'M':
#         j = 3
#     elif classification == 'O':
#         j = 4
#     elif classification == 'S':
#         j = 5
#     else:
#         raise ValueError
#     if ci.introduction_count > 0:
#         severity_experience_dc.update('introduction_count', i, j, ci.introduction_count)
#     severity_experience_dc.update('lines_changed', i, j, ci.lines_changed)
# severity_experience_dc.write_csv('severity-experience')

# # Fix-Commit Changes
# changes = ['none', 'add', 'mod', 'rm', 'add/mod', 'add/rm', 'mod/rm', 'all']
# changes_dc = DataCollector(['total_commits'],
#                            'total_commits',
#                            changes)
# for bug in Bug.objects.filter(fix_commits__author__repository=r):
#     ci = bug.fix_commits.all()[0].commitinformation
#     if not ci.merge:
#         if ci.lines_modified == 0 and ci.lines_removed == 0 and ci.lines_added == 0:
#             changes_dc.update('total_commits', 'none', amount=1)
#         elif ci.lines_modified > 0 and ci.lines_removed == 0 and ci.lines_added == 0:
#             changes_dc.update('total_commits', 'mod')
#         elif ci.lines_modified == 0 and ci.lines_removed > 0 and ci.lines_added == 0:
#             changes_dc.update('total_commits', 'rm')
#         elif ci.lines_modified == 0 and ci.lines_removed == 0 and ci.lines_added > 0:
#             changes_dc.update('total_commits', 'add')
#         elif ci.lines_modified == 0 and ci.lines_removed > 0 and ci.lines_added > 0:
#             changes_dc.update('total_commits', 'add/rm')
#         elif ci.lines_modified > 0 and ci.lines_removed == 0 and ci.lines_added > 0:
#             changes_dc.update('total_commits', 'add/mod')
#         elif ci.lines_modified > 0 and ci.lines_removed > 0 and ci.lines_added == 0:
#             changes_dc.update('total_commits', 'mod/rm')
#         else:
#             changes_dc.update('total_commits', 'all')
# changes_dc.write_csv('changes')
