# Secrets Manager entries. Terraform seeds empty placeholders — operators run
# `aws secretsmanager put-secret-value` after the first apply (see README).
# Rotation is left manual; enable it per-secret when the app supports dual-key
# rollovers.

resource "aws_secretsmanager_secret" "app" {
  for_each = toset(local.app_secret_names)

  name                    = "${local.name_prefix}/${each.value}"
  description             = "${var.project_name} ${var.environment} — ${each.value}"
  recovery_window_in_days = 7

  tags = {
    Name   = "${local.name_prefix}-${each.value}"
    Secret = each.value
  }
}

resource "aws_secretsmanager_secret_version" "app_placeholder" {
  for_each = aws_secretsmanager_secret.app

  secret_id     = each.value.id
  secret_string = "REPLACE_VIA_PUT_SECRET_VALUE"

  lifecycle {
    # Never overwrite operator-managed secret values on subsequent applies.
    ignore_changes = [secret_string, version_stages]
  }
}
