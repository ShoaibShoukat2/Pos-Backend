from django.db import migrations, models
import uuid


def populate_slugs(apps, schema_editor):
    """Give each existing business a unique slug."""
    Business = apps.get_model("businesses", "Business")
    for biz in Business.objects.all():
        from django.utils.text import slugify
        base = slugify(biz.name) or "shop"
        slug = base[:60]
        if Business.objects.filter(price_checker_slug=slug).exclude(pk=biz.pk).exists():
            slug = f"{base[:50]}-{str(uuid.uuid4())[:6]}"
        biz.price_checker_slug = slug
        biz.save(update_fields=["price_checker_slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0005_add_brand_colors"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="price_checker_enabled",
            field=models.BooleanField(default=False),
        ),
        # Add without unique first, populate, then make unique
        migrations.AddField(
            model_name="business",
            name="price_checker_slug",
            field=models.SlugField(
                blank=True,
                help_text="URL slug for the public price checker, e.g. 'al-noor-traders'",
                max_length=80,
                unique=False,
            ),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="business",
            name="price_checker_slug",
            field=models.SlugField(
                blank=True,
                help_text="URL slug for the public price checker, e.g. 'al-noor-traders'",
                max_length=80,
                unique=True,
            ),
        ),
    ]
