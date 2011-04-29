from django.db import models

class Repository(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=50)
    description = models.TextField()
    first_commit = models.ForeignKey("RawCommit", blank=True, null=True,
                                     related_name="repostiory_first_commit")
    last_commit = models.ForeignKey("RawCommit", blank=True, null=True,
                                    related_name="repostiory_last_commit")

class RawAuthor(models.Model):
    repository = models.ForeignKey(Repository)
    name = models.CharField(max_length=75)
    email = models.CharField(max_length=75)
    author = models.ForeignKey("Author", blank=True, null=True)

    class Meta:
        unique_together = ("repository", "name", "email")

class RawCommit(models.Model):
    author = models.ForeignKey(RawAuthor)
    sha1 = models.CharField(max_length=40, db_index=True)
    merge = models.BooleanField()
    utc_time = models.DateTimeField()
    local_time = models.DateTimeField()

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

    def total_commits(self):
        return RawCommit.objects.filter(author__in=
                                        self.rawauthor_set.all()).count()

class Commit(models.Model):
    commit = models.OneToOneField(RawCommit, primary_key=True)
    lines_changed_code = models.PositiveIntegerField()
    lines_changed_comments = models.PositiveIntegerField()
    lines_changed_other = models.PositiveIntegerField()

class Bug(models.Model):
    introducing_commits = models.ManyToManyField(RawCommit,
        related_name="bug_introductions", through="BugSource")
    fix_commit = models.OneToOneField(RawCommit, primary_key=True)

class BugSource(models.Model):
    commit = models.ForeignKey(RawCommit)
    bug = models.ForeignKey(Bug)
    files = models.ManyToManyField("File", related_name="bug_sources")

class File(models.Model):
    name = models.CharField(max_length=256)
