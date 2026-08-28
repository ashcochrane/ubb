"""The close declares WHY, beside declaring how it ended (#409).

Two columns arrive together and neither has a writer before this commit: the
caller's closed-set `outcome_reason`, and the free-text `reason_detail` beside
it. Two rather than one is #140 §3.3's cardinality argument made physical — the
code is a small set a dashboard can group on, the sentence is the provider's
own message and is display-only, and merging them would make every distinct
provider string its own bucket.

**PURE ADDITION, AND NO ROW IS REWRITTEN.** Both default to `""`, which is the
honest value for every row that exists: a unit closed before this commit was
closed by a call that could not carry a reason, so there is nothing to
back-fill and nothing to guess. `""` therefore means exactly *nobody gave one*
wherever it appears, and it goes on meaning that afterwards — on a delivery,
where neither field is accepted, and on a `killed` or `expired` unit, where no
caller declared anything at all.

**THE REVERSE IS EXACT**: dropping two columns nothing else references, whose
whole content is a declaration this commit introduced the ability to make.

⚠ THESE ARE NOT THE STOP REASON, AND THE TWO MUST NOT BE MERGED LATER.
`metadata["kill_reason"]` carries the OTHER concept — open, UBB-produced, and
slice 6's — and its separation from this one is ruled in
`OUTCOME_REASON_CHOICES` in the model beside it.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work', '0017_six_lifecycle_states_and_completed_means_one_thing'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='outcome_reason',
            field=models.CharField(blank=True, choices=[('upstream_provider_error', 'Upstream provider error'), ('timeout', 'Timeout'), ('invalid_input', 'Invalid input'), ('internal_error', 'Internal error'), ('execution_failed', 'Execution failed'), ('customer_cancelled', 'Customer cancelled'), ('superseded', 'Superseded'), ('parent_closed', 'Parent closed'), ('unspecified', 'Unspecified')], default='', max_length=32),
        ),
        migrations.AddField(
            model_name='task',
            name='reason_detail',
            field=models.TextField(blank=True, default=''),
        ),
    ]
