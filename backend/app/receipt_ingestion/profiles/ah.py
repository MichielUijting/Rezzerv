from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .base import (
    ProfileDetection,
    ProfileDiagnostics,
    ProfileLineClassification,
    READ_ONLY_PROFILE_GUARDRAILS,
)


AMOUNT_RE = re.compile(r'(?<!\d)-?\d{1,5}(?:[\.,]\d{2})(?!\d)')
CONFLICTING_CHAINS = ('jumbo', 'lidl', 'aldi', 'plus')


class AhReceiptProfile:
    chain_id = 'ah'
    display_name = 'Albert Heijn'

    def _norm(self, value: str) -> str:
        return re.sub(r'\s+', ' ', str(value or '')).strip().lower()

    def _amount(self, value: str) -> str | None:
        matches = AMOUNT_RE.findall(str(value or ''))
        return matches[-1] if matches else None

    def detect(self, lines: list[str]) -> ProfileDetection:
        haystack = '\n'.join(str(line or '') for line in lines)
        lowered = haystack.lower()
        score = 0
        evidence: list[str] = []
        conflicts: list[str] = []

        if re.search(r'\balbert\s*heijn\b', lowered):
            score += 60
            evidence.append('explicit_albert_heijn')
        if re.search(r'\bah\b', lowered) and any(token in lowered for token in ('bonus', 'totaal', 'kassabon', 'betaling')):
            score += 50
            evidence.append('ah_with_receipt_context')
        if 'ah.nl' in lowered or 'ahold' in lowered:
            score += 40
            evidence.append('ah_domain_or_ahold')
        if 'bonus box' in lowered:
            score += 30
            evidence.append('bonus_box')
        elif 'bonus' in lowered:
            score += 20
            evidence.append('bonus')
        if any(token in lowered for token in ('koopzegels', 'persoonlijke bonus', 'mijn ah')):
            score += 15
            evidence.append('ah_loyalty_signal')

        for chain in CONFLICTING_CHAINS:
            if re.search(rf'\b{re.escape(chain)}\b', lowered):
                score -= 100
                conflicts.append(chain)

        if score >= 70:
            confidence = 'high'
        elif score >= 40:
            confidence = 'medium'
        elif score > 0:
            confidence = 'low'
        else:
            confidence = 'none'

        return ProfileDetection(
            chain_id=self.chain_id,
            display_name=self.display_name,
            confidence=confidence,
            score=score,
            evidence=evidence,
            conflicts=conflicts,
        )

    def _section_for_line(self, line: str, prior_section: str) -> tuple[str, list[str]]:
        text = self._norm(line)
        signals: list[str] = []
        if not text:
            return 'noise', ['empty']
        if any(token in text for token in ('totaal', 'te betalen', 'eindtotaal')):
            return 'total', ['total_marker']
        if any(token in text for token in ('pin', 'bankpas', 'maestro', 'visa', 'betaling', 'betaald', 'wisselgeld', 'contactloos')):
            return 'payment', ['payment_marker']
        if any(token in text for token in ('btw', 'bedrag excl', 'bedrag incl', 'tel.', 'klantenservice', 'www.', 'ah.nl', 'bedankt')):
            return 'vat_footer', ['vat_or_footer_marker']
        if any(token in text for token in ('bonus', 'korting', 'persoonlijke bonus', 'bonus box')) or re.search(r'-\s*\d+[\.,]\d{2}', text):
            return 'discount', ['discount_marker']
        if any(token in text for token in ('albert heijn', 'ah ', 'filiaal', 'kassa', 'bonnr', 'transactie')):
            return 'header', ['header_marker']
        if self._amount(line):
            return 'article_block', ['amount_present']
        return prior_section if prior_section in {'article_block', 'discount'} else 'header'

    def classify_lines(self, lines: list[str]) -> list[ProfileLineClassification]:
        result: list[ProfileLineClassification] = []
        prior_section = 'header'
        for index, line in enumerate(lines, start=1):
            amount = self._amount(line)
            section, signals = self._section_for_line(line, prior_section)
            text = self._norm(line)

            if section == 'total':
                line_class = 'total_candidate'
                reason = 'hard total marker'
            elif section == 'payment':
                line_class = 'payment_candidate'
                reason = 'hard payment marker'
            elif section == 'vat_footer':
                line_class = 'vat_footer_candidate'
                reason = 'VAT/footer marker'
            elif section == 'discount':
                line_class = 'discount_candidate'
                reason = 'bonus/discount marker or negative amount'
            elif amount and re.search(r'\b\d+\s+', text):
                line_class = 'article_candidate'
                reason = 'quantity or leading number plus label plus amount; no hard payment/total marker'
                signals.append('quantity_or_multibuy_signal')
            elif amount:
                line_class = 'article_candidate'
                reason = 'label plus amount; no hard payment/total marker'
            elif section == 'header':
                line_class = 'header'
                reason = 'header or store context line'
            else:
                line_class = 'noise'
                reason = 'no AH article or fiscal marker'

            if 'chips' in text and amount and line_class != 'article_candidate':
                line_class = 'article_candidate'
                reason = 'CHIPS with amount is product text unless hard payment/total marker is present'
                signals.append('chips_product_guard')

            result.append(ProfileLineClassification(
                index=index,
                text=str(line or ''),
                section=section,
                line_class=line_class,
                reason=reason,
                amount=amount,
                signals=signals,
            ))
            if section != 'noise':
                prior_section = section
        return result

    def diagnostics(self, lines: list[str]) -> ProfileDiagnostics:
        detection = self.detect(lines)
        classifications = self.classify_lines(lines)
        counts = Counter(item.line_class for item in classifications)
        section_counts = Counter(item.section for item in classifications)
        summary: dict[str, Any] = {
            'line_count': len(lines),
            'class_counts': dict(counts),
            'section_counts': dict(section_counts),
            'article_candidate_count': counts.get('article_candidate', 0),
            'discount_candidate_count': counts.get('discount_candidate', 0),
            'payment_candidate_count': counts.get('payment_candidate', 0),
            'total_candidate_count': counts.get('total_candidate', 0),
        }
        return ProfileDiagnostics(
            profile=self.chain_id,
            detection=detection,
            line_classifications=classifications,
            summary=summary,
            guardrails=READ_ONLY_PROFILE_GUARDRAILS,
        )
