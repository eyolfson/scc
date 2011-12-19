import argparse
import csv
from datetime import datetime, timedelta
import gmpy
import math
import os
import sys

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


# Command line parser
parser = argparse.ArgumentParser(description="Python script to generate results from the SCC database.")
parser.add_argument("--log", action='store_true', help="enable logging")
args = parser.parse_args()


WEEK_DAY_CHOICES = (
    (2, "Mon"),
    (3, "Tues"),
    (4, "Wed"),
    (5, "Thur"),
    (6, "Fri"),
    (7, "Sat"),
    (1, "Sun"))



# Logging functions
if args.log:
    def get_log_file():
        if not os.path.exists(log_dir):
            os.mkdir(log_dir)
        log_filename = "results_%s.log" % datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        return codecs.open(os.path.join(log_dir, log_filename), "w", "utf-8")

    log_dir = "log"
    log_file = get_log_file()

    def log(msg):
        time_stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        log_file.write("[%s] %s\n" % (time_stamp, msg))
        log_file.flush()
else:
    def log(msg):
        pass

def introducing_commits_count(repository, **kwargs):
    return repository.commits_introducing().filter(**kwargs).count()
    # adjusted_kwargs = {}
    # for kv in kwargs.iteritems():
    #     adjusted_kwargs["rawcommit__%s" % kv[0]] = kv[1]
    # return models.BugSource.objects.filter(rawcommit__rawauthor__repository=repository, **adjusted_kwargs).values("rawcommit").distinct().count()

def introducing_commits_count_hour(repository, hour, **kwargs):
    return repository.commits_introducing().filter(basic_information__hour=hour, **kwargs).count()
    # adjusted_kwargs = {}
    # for kv in kwargs.iteritems():
    #     adjusted_kwargs["rawcommit__%s" % kv[0]] = kv[1]
    # return models.BugSource.objects.filter(rawcommit__rawauthor__repository=repository, **adjusted_kwargs).extra(where=['EXTRACT(\'hour\' FROM "scc_rawcommit"."local_time") = %d' % hour]).values("rawcommit").distinct().count()

def commits_count(repository, **kwargs):
    return repository.commits.filter(**kwargs).count()
    # return models.RawCommit.objects.filter(rawauthor__repository=repository, **kwargs).count()

def commits_count_hour(repository, hour, **kwargs):
    return repository.commits.filter(basic_information__hour=hour, **kwargs).count()
    # return models.RawCommit.objects.filter(rawauthor__repository=repository, **kwargs).extra(where=['EXTRACT(\'hour\' FROM "scc_rawcommit"."local_time") = %d' % hour]).count()

def calculate_p_value(expected_prob, actual, total):
    try:
        actual_prob = float(actual)/float(total)
    except ZeroDivisionError:
        return 0.0
    
    # Determine the range based on whether or not the actual probability is more or less than expected
    if (actual_prob > expected_prob):
        value_range = xrange(actual, total + 1)
    else:
        value_range = xrange(actual + 1)

    # Calculate the P-value with 128 bits of precision
    bits = 128
    p_value = 0.0
    for i in value_range:
        p_value += gmpy.comb(total, i) * (gmpy.mpf(expected_prob, bits) ** i) * (gmpy.mpf((1.0 - expected_prob), bits) ** (total - i))
    return p_value

def bugginess_day(repository):

    filename = filename_format % ("%s_bugginess_day" % repository.slug)
    if os.path.exists(filename):
        return
    
    rows = [x[1] for x in WEEK_DAY_CHOICES]
    columns = ["Introducing Commits", "Commits", "% Buggy Commits", "P-value"]

    data = [[0 for j in xrange(2)] for i in xrange(len(rows)+1)]
    overall_row = len(rows)

    i = 0
    for week_day in WEEK_DAY_CHOICES:
        kwargs = {"local_time__week_day": week_day[0]}
        introducing_commits = introducing_commits_count(repository, **kwargs)
        commits = commits_count(repository, **kwargs)

        data[i][0] += introducing_commits
        data[i][1] += commits

        data[overall_row][0] += introducing_commits
        data[overall_row][1] += commits

        i += 1
    del i
    overall_percent_buggy_commits = float(data[overall_row][0])/float(data[overall_row][1])

    writer = csv.writer(open(filename, "wb"))
    writer.writerow(["Day"] + columns)
    for i in xrange(len(rows)):
        percent_buggy_commits = float(data[i][0])/float(data[i][1])
        p_value = calculate_p_value(overall_percent_buggy_commits, data[i][0], data[i][1])
        writer.writerow([rows[i]] + data[i] + [percent_buggy_commits, p_value])
    writer.writerow(["Overall"] + data[overall_row] + [overall_percent_buggy_commits])

def bugginess_hour(repository):
    filename = filename_format % ("%s_bugginess_hour" % repository.slug)
    if os.path.exists(filename):
        return

    rows = range(24)
    columns = ["Introducing Commits", "Commits", "% Buggy Commits", "P-value"]

    data = [[0 for j in xrange(2)] for i in xrange(len(rows)+1)]
    overall_row = len(rows)

    i = 0
    for hour in rows:
        introducing_commits = introducing_commits_count_hour(repository, hour)
        commits = commits_count_hour(repository, hour)

        data[i][0] += introducing_commits
        data[i][1] += commits

        data[overall_row][0] += introducing_commits
        data[overall_row][1] += commits

        i += 1
    del i

    overall_percent_buggy_commits = float(data[overall_row][0])/float(data[overall_row][1])

    writer = csv.writer(open(filename, "wb"))
    writer.writerow(["Hour"] + columns)
    for i in xrange(len(rows)):
        percent_buggy_commits = float(data[i][0])/float(data[i][1])
        p_value = calculate_p_value(overall_percent_buggy_commits, data[i][0], data[i][1])
        writer.writerow([rows[i]] + data[i] + [percent_buggy_commits, p_value])
    writer.writerow(["Overall"] + data[overall_row] + [overall_percent_buggy_commits])

def bugginess_frequency(repository):
    filename = filename_format % ("%s_bugginess_frequency" % repository.slug)
    if os.path.exists(filename):
        return
    
    rows = [x[1] for x in models.AuthorClassificationInformation.CLASSIFICATION_CHOICES]
    columns = ["Introducing Commits", "Commits", "% Buggy Commits", "P-value"]

    data = [[0 for j in xrange(2)] for i in xrange(len(rows)+1)]
    overall_row = len(rows)

    i = 0
    for classification in models.AuthorClassificationInformation.CLASSIFICATION_CHOICES:
        kwargs = {"raw_author__author__classification_information__classification": classification[0]}
        introducing_commits = introducing_commits_count(repository, **kwargs)
        commits = commits_count(repository, **kwargs)

        data[i][0] += introducing_commits
        data[i][1] += commits

        data[overall_row][0] += introducing_commits
        data[overall_row][1] += commits

        i += 1
    del i
    overall_percent_buggy_commits = float(data[overall_row][0])/float(data[overall_row][1])

    writer = csv.writer(open(filename, "wb"))
    writer.writerow(["Frequency"] + columns)
    for i in xrange(len(rows)):
        try:
            percent_buggy_commits = float(data[i][0])/float(data[i][1])
        except ZeroDivisionError:
            percent_buggy_commits = 0.0
        p_value = calculate_p_value(overall_percent_buggy_commits, data[i][0], data[i][1])
        writer.writerow([rows[i]] + data[i] + [percent_buggy_commits, p_value])
    writer.writerow(["Overall"] + data[overall_row] + [overall_percent_buggy_commits])

def bugginess_experience(repository):
    filename = filename_format % ("%s_bugginess_experience" % repository.slug)
    if os.path.exists(filename):
        return
    
    last_utc_time = repository.last_commit.utc_time
    first_utc_time = repository.first_commit.utc_time

    rows = range(120, (last_utc_time - first_utc_time).days + 120, 120)
    columns = ["Introducing Commits", "Commits", "% Buggy Commits", "P-value"]

    data = [[0 for j in xrange(2)] for i in xrange(len(rows)+1)]
    overall_row = len(rows)

    authors = {}
    for author in models.Author.objects.filter(raw_authors__repository=repository).distinct():
        author_first_utc_time = last_utc_time + timedelta(1)
        for rawauthor in author.raw_authors.all():
            for rawcommit in rawauthor.commits.order_by("utc_time"):
                if rawcommit.utc_time >= first_utc_time:
                    if rawcommit.utc_time < author_first_utc_time:
                        author_first_utc_time = rawcommit.utc_time
                    break
        authors[author.pk] = author_first_utc_time

    for rawcommit in models.Commit.objects.filter(repository=repository):
        if rawcommit.utc_time >= first_utc_time and rawcommit.utc_time <= last_utc_time:
            experience = (rawcommit.utc_time - authors[rawcommit.raw_author.author.pk]).days
        else:
            continue

        i = experience/120
        if rawcommit.basic_information.is_introducing:
            data[i][0] += 1
            data[overall_row][0] += 1

        data[i][1] += 1
        data[overall_row][1] += 1

    overall_percent_buggy_commits = float(data[overall_row][0])/float(data[overall_row][1])

    writer = csv.writer(open(filename, "wb"))
    writer.writerow(["Experience"] + columns)
    for i in xrange(len(rows)):
        try:
            percent_buggy_commits = float(data[i][0])/float(data[i][1])
        except ZeroDivisionError:
            percent_buggy_commits = 0.0
        p_value = calculate_p_value(overall_percent_buggy_commits, data[i][0], data[i][1])
        writer.writerow([rows[i]] + data[i] + [percent_buggy_commits, p_value])
    writer.writerow(["Overall"] + data[overall_row] + [overall_percent_buggy_commits])

def bugginess_hour_experienced(repository):
    filename = filename_format % ("%s_bugginess_hour_experienced" % repository.slug)
    if os.path.exists(filename):
        return
    
    last_utc_time = repository.last_commit.utc_time
    first_utc_time = repository.first_commit.utc_time

    rows = range(24)
    categories = ["< 2 years experience", ">= 2 years experience"]
    columns = ["Introducing Commits", "Commits", "% Buggy Commits", "P-value"]

    data = [[0 for j in xrange(4)] for i in xrange(len(rows)+2)]
    overall_category_row = len(rows)
    overall_row = len(rows)+1

    authors = {}
    for author in models.Author.objects.filter(raw_authors__repository=repository).distinct():
        author_first_utc_time = last_utc_time + timedelta(1)
        for rawauthor in author.raw_authors.all():
            for rawcommit in rawauthor.commits.order_by("utc_time"):
                if rawcommit.utc_time >= first_utc_time:
                    if rawcommit.utc_time < author_first_utc_time:
                        author_first_utc_time = rawcommit.utc_time
                    break
        authors[author.pk] = author_first_utc_time

    for rawcommit in models.Commit.objects.filter(repository=repository):
        if rawcommit.utc_time >= first_utc_time and rawcommit.utc_time <= last_utc_time:
            experience = (rawcommit.utc_time - authors[rawcommit.raw_author.author.pk]).days
        else:
            continue

        i = rawcommit.local_time.hour
        if experience < 731:
            if rawcommit.basic_information.is_introducing:
                data[i][0] += 1
                data[overall_category_row][0] += 1
                data[overall_row][0] += 1
            data[i][1] += 1
            data[overall_category_row][1] += 1
            data[overall_row][1] += 1
        else:
            if rawcommit.basic_information.is_introducing:
                data[i][2] += 1
                data[overall_category_row][2] += 1
                data[overall_row][0] += 1
            data[i][3] += 1
            data[overall_category_row][3] += 1
            data[overall_row][1] += 1            

    category_1_overall_percent_buggy_commits = float(data[overall_category_row][0])/float(data[overall_category_row][1])
    category_2_overall_percent_buggy_commits = float(data[overall_category_row][2])/float(data[overall_category_row][3])
    overall_percent_buggy_commits = float(data[overall_row][0])/float(data[overall_row][1])

    writer = csv.writer(open(filename, "wb"))
    writer.writerow([""] + [categories[0]] + ([""] * 3) + [categories[1]])
    writer.writerow(["Hour"] + (columns * len(categories)))
    for i in xrange(len(rows)):
        try:
            percent_buggy_commits = float(data[i][0])/float(data[i][1])
        except ZeroDivisionError:
            percent_buggy_commits = 0.0
        p_value = calculate_p_value(overall_percent_buggy_commits, data[i][0], data[i][1])
        try:
            category_2_percent_buggy_commits = float(data[i][0])/float(data[i][1])
        except ZeroDivisionError:
            category_2_percent_buggy_commits = 0.0
        category_2_p_value = calculate_p_value(overall_percent_buggy_commits, data[i][2], data[i][3])

        writer.writerow([rows[i]] + data[i][:2] + [percent_buggy_commits, p_value] + data[i][2:] + [category_2_percent_buggy_commits, category_2_p_value])
    writer.writerow(["Category Overall"] + data[overall_category_row][:2] + [category_1_overall_percent_buggy_commits] + [""] + data[overall_category_row][2:] + [category_2_overall_percent_buggy_commits])
    writer.writerow(["Overall"] + data[overall_row][:2] + [overall_percent_buggy_commits])

filename_format = "results_csv/%s.csv"

for repository in [models.Repository.objects.get(slug='xorg')]:
    bugginess_day(repository)
    bugginess_hour(repository)
    bugginess_frequency(repository)
    bugginess_experience(repository)
    bugginess_hour_experienced(repository)
