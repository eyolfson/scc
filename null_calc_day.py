from math import pow
from gmpy import comb
import gmpy


how_many = 7
commits_file = 'results/linux-commits-day.csv'
other_file = 'results/linux-bugginess-day.csv'

import csv
data = [[0,0] for i in xrange(how_many + 1)]

reader = csv.reader(open(commits_file, 'r'))
i = 0
skip = True
for row in reader:
    if skip:
        skip = False
        continue
    data[i][1] = float(row[7])
    i += 1

reader = csv.reader(open(other_file, 'r'))
i = 0
skip = True
for row in reader:
    if skip:
        skip = False
        continue
    data[i][0] = round(float(row[7]) * int(data[i][1]))/100.0
    i += 1


p = data[how_many][0] / data[how_many][1]
bits = 128

writer = csv.writer(open('null_calc.csv', 'w'))
r = 0
for d in data[:-1]:

    if (d[0]/d[1]) > p:
        is_at_least = True
    else:
        is_at_least = False

    value = int(d[0])
    total = int(d[1])
    p_value = 0
    if not is_at_least:
        calc_range  = xrange(value + 1)
    else:
        calc_range = xrange(value, total + 1)

    for i in calc_range:
        p_value += gmpy.comb(total, i) * (gmpy.mpf(p, bits) ** i) * (gmpy.mpf((1 - p), bits) ** (total - i))

    print d, p_value
    writer.writerow([r, p_value])

    r += 1


# p = 0.5
# value = 14
# total = 20
# is_at_least = True

# p = 56680.0/222331.0
# value = 1642
# total = 5300
# is_at_least = True

# p_value = 0
# if not is_at_least:
#     calc_range  = xrange(value + 1)
# else:
#     calc_range = xrange(value, total + 1)

# for i in calc_range:
#     p_value += gmpy.comb(total, i) * (gmpy.mpf(p, bits) ** i) * (gmpy.mpf((1 - p), bits) ** (total - i))
#     # print "C(%d, %d) * p^%d * (1-p)^%d" % (total, i, i, total - i)
# print p_value
