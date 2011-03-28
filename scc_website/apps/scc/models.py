from django.db import models

class Repository(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=50)
    description = models.TextField()
    first_commit = models.ForeignKey("RawCommit", blank=True, null=True,
                                     related_name="repostiory_first_commit")
    last_commit = models.ForeignKey("RawCommit", blank=True, null=True,
                                    related_name="repostiory_last_commit")

class Author(models.Model):
    CLASSIFICATION_CHOICES = (
        ('J', "Job"),
        ('D', "Daily"),
        ('W', "Weekly"),
        ('M', "Monthly"),
        ('O', "Other"),
        ('S', "Single"),
    )
    name = models.CharField(max_length=75)
    email = models.CharField(max_length=75)
    classification = models.CharField(max_length=1,
                                      choices=CLASSIFICATION_CHOICES,
                                      blank=True, null=True)

class RawAuthor(models.Model):
    repository = models.ForeignKey(Repository)
    name = models.CharField(max_length=75)
    email = models.CharField(max_length=75)
    author = models.ForeignKey(Author, blank=True, null=True)

    class Meta:
        unique_together = ("repository", "name", "email")

class RawCommit(models.Model):
    author = models.ForeignKey(RawAuthor)
    sha1 = models.CharField(max_length=40)
    merge = models.BooleanField()
    utc_time = models.DateTimeField()
    local_time = models.DateTimeField()

class File(models.Model):
    name = models.CharField(max_length=100)

class Bug(models.Model):
    introducing_commits = models.ManyToManyField(RawCommit,
        related_name="bug_introductions", through="BugSource")
    fix_commit = models.ForeignKey(RawCommit, unique=True)

class BugSource(models.Model):
    commit = models.ForeignKey(RawCommit)
    bug = models.ForeignKey(Bug)
    files = models.ManyToManyField(File, related_name="bug_sources")
