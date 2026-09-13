from __future__ import annotations


def resolve_auto_consume_effective_mode_all_articles(
    main_module,
    household_mode: str,
    article_override: str,
    _consumable: bool,
) -> str:
    """Temporarily let every article participate in household auto-consume.

    Stored/catalog consumable data stays untouched. This policy only affects the
    household-automation decision until Catalogus becomes the canonical authority
    for consumable classification. See GitHub issue #427.
    """
    effective_mode = household_mode
    if article_override == main_module.ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY:
        effective_mode = main_module.ARTICLE_AUTO_CONSUME_PURCHASED_QUANTITY
    elif article_override == main_module.ARTICLE_AUTO_CONSUME_ALL_EXISTING:
        effective_mode = main_module.ARTICLE_AUTO_CONSUME_ALL_EXISTING
    elif article_override == main_module.ARTICLE_AUTO_CONSUME_NONE:
        effective_mode = main_module.ARTICLE_AUTO_CONSUME_NONE

    return (
        effective_mode
        if effective_mode in main_module.HOUSEHOLD_AUTO_CONSUME_ALLOWED
        else main_module.ARTICLE_AUTO_CONSUME_NONE
    )


def install_temporary_all_articles_consumable_policy(main_module) -> None:
    app = main_module.app
    if getattr(app.state, "temporary_all_articles_consumable_policy_installed", False):
        return

    def resolve_auto_consume_effective_mode(
        household_mode: str,
        article_override: str,
        consumable: bool,
    ) -> str:
        return resolve_auto_consume_effective_mode_all_articles(
            main_module,
            household_mode,
            article_override,
            consumable,
        )

    # Intentional temporary product policy. Do not rewrite household_articles data.
    # Remove this installer when issue #427 introduces Catalogus as authority.
    main_module.resolve_auto_consume_effective_mode = resolve_auto_consume_effective_mode
    app.state.temporary_all_articles_consumable_policy_installed = True
