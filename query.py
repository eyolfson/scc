import csv, os
from datetime import datetime
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.repositories.models import *

# r = Repository.objects.get(pk=1)
# exclude_pk = 222332

r = Repository.objects.get(pk=4)
exclude_pk = 532279

ci_set = CommitInformation.objects.filter(commit__author__repository=r).exclude(commit__pk=exclude_pk)

days = ['Mon', 'Tues', 'Wed', 'Thur', 'Fri', 'Sat', 'Sun']
classes = ['Job', 'Daily', 'Weekly', 'Monthly', 'Other', 'Single']
hours = range(24)

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
        
        if category is not DataCollector.OVERALL_CATEGORY:
            j = len(self._variable_map)*self._category_map[DataCollector.OVERALL_CATEGORY]+self._variable_map[variable]
            self._data[i][j] += amount
            self._data[len(self._row_map)][j] += amount

    def write_csv(self, filename):
        # Open the file and write the header
        import csv
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

# Severity per Day
severity_day_dc = DataCollector(['introduction_count', 'lines_changed'],
                                 'div(introduction_count, lines_changed)',
                                 days,
                                 classes)
for ci in ci_set:
    i = ci.commit.local_time.weekday()
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
    if ci.introduction_count > 0:
        severity_day_dc.update('introduction_count', i, j, ci.introduction_count)
    severity_day_dc.update('lines_changed', i, j, ci.lines_changed)
severity_day_dc.write_csv('severity-day')

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
