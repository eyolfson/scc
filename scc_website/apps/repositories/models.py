from django.db import models

class Repository(models.Model):
    name = models.CharField(max_length=75)
    description = models.TextField()

class Author(models.Model):
    repository = models.ForeignKey(Repository)
    name = models.CharField(max_length=75)
    email = models.CharField(max_length=75)

class Commit(models.Model):
    author = models.ForeignKey(Author)
    sha1 = models.CharField(max_length=40)
    utc_time = models.DateTimeField()
    local_time = models.DateTimeField()

class Bug(models.Model):
    introduction_commits = models.ManyToManyField(Commit, related_name='introductions')
    fix_commits = models.ManyToManyField(Commit, related_name='fixes')

class AuthorInformation(models.Model):
    CLASSIFICATION_CHOICES = (
        ('D', 'Daily'),
        ('W', 'Weekly'),
        ('M', 'Monthly'),
        ('S', 'Single'),
    )
    author = models.OneToOneField(Author, primary_key=True)
    classification = models.CharField(max_length=1, choices=CLASSIFICATION_CHOICES)
    day_job = models.BooleanField()
    experience = models.IntegerField()
