// Report wizard shell — 5-step guided flow replacing the two-panel builder.
// Implements steps 1 (Select) and 2 (Configure); steps 3–5 are placeholders.
// REQ-U-01 / REQ-U-11 / REQ-C-10..15 / REQ-C-26

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/services/nsight_api.dart';
import '../providers/builder_provider.dart';
import '../providers/reports_provider.dart';
import '../../data/providers/material_provider.dart';
import 'step_select.dart';
import 'step_configure.dart';
import 'step_review.dart';
import 'step_slides.dart';
import 'step_download.dart';

// ---------------------------------------------------------------------------
// Wizard step labels
// ---------------------------------------------------------------------------

const _kStepLabels = ['Select', 'Configure', 'Review', 'Slides', 'Download'];

// ---------------------------------------------------------------------------
// ReportWizard widget
// ---------------------------------------------------------------------------

/// 5-step wizard that guides the user through building a report.
///
/// Steps 1 (Select) and 2 (Configure with live preview) are implemented here.
/// Steps 3–5 show a "coming next" placeholder and will be wired in W3.
///
/// Replaces [ReportBuilder] as the primary report-editing surface. (REQ-U-01)
class ReportWizard extends ConsumerStatefulWidget {
  const ReportWizard({
    super.key,
    required this.caseId,
    required this.reportId,
  });

  final String caseId;
  final String reportId;

  @override
  ConsumerState<ReportWizard> createState() => _ReportWizardState();
}

class _ReportWizardState extends ConsumerState<ReportWizard> {
  int _step = 0;
  final _nameController = TextEditingController();
  bool _nameInitialized = false;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        ref
            .read(builderProvider.notifier)
            .load(widget.caseId, widget.reportId);
      }
    });
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(builderProvider);

    if (draft != null && !_nameInitialized) {
      _nameController.text = draft.name;
      _nameInitialized = true;
    }

    if (draft == null) {
      return const Center(child: CircularProgressIndicator());
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildTopBar(context, draft),
        const Divider(height: 1),
        _buildStepIndicator(context),
        const Divider(height: 1),
        Expanded(child: _buildStepBody(context, draft)),
        const Divider(height: 1),
        _buildNavBar(context, draft),
      ],
    );
  }

  // ── Top bar ───────────────────────────────────────────────────────────────

  Widget _buildTopBar(BuildContext context, ReportDraft draft) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          IconButton(
            key: const Key('wizard_back_button'),
            icon: const Icon(Icons.arrow_back),
            tooltip: 'Back to reports list',
            onPressed: () {
              ref.read(builderProvider.notifier).reset();
              ref.read(selectedReportProvider.notifier).select(null);
            },
          ),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              key: const Key('wizard_name_field'),
              controller: _nameController,
              decoration: const InputDecoration(
                labelText: 'Report name',
                isDense: true,
                border: OutlineInputBorder(),
              ),
              onChanged: (v) =>
                  ref.read(builderProvider.notifier).setName(v),
            ),
          ),
          const SizedBox(width: 8),
          ElevatedButton.icon(
            key: const Key('wizard_save_button'),
            onPressed: _saving ? null : () => _save(context),
            icon: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.save),
            label: const Text('Save'),
          ),
        ],
      ),
    );
  }

  // ── Step indicator ────────────────────────────────────────────────────────

  Widget _buildStepIndicator(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      color: theme.colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
      child: Row(
        children: [
          for (int i = 0; i < _kStepLabels.length; i++) ...[
            if (i > 0)
              Expanded(
                child: Container(
                  height: 2,
                  color: i <= _step
                      ? theme.colorScheme.primary
                      : theme.dividerColor,
                ),
              ),
            _StepChip(
              step: i + 1,
              label: _kStepLabels[i],
              isActive: i == _step,
              isCompleted: i < _step,
            ),
          ],
        ],
      ),
    );
  }

  // ── Step body ─────────────────────────────────────────────────────────────

  Widget _buildStepBody(BuildContext context, ReportDraft draft) {
    final materialId = ref.watch(activeMaterialProvider);
    switch (_step) {
      case 0:
        return SelectStep(
          key: const Key('select_step'),
          onQuestionsAdded: () => setState(() => _step = 1),
        );
      case 1:
        return ConfigureStep(
          key: const Key('configure_step'),
          materialId: materialId,
          caseId: widget.caseId,
        );
      case 2:
        return ReviewStep(
          key: const Key('review_step'),
          materialId: materialId,
        );
      case 3:
        return SlidesStep(
          key: const Key('slides_step'),
          materialId: materialId,
        );
      case 4:
        return DownloadStep(
          key: const Key('download_step'),
          caseId: widget.caseId,
          reportId: widget.reportId,
        );
      default:
        return const _PlaceholderStep();
    }
  }

  // ── Bottom navigation bar ─────────────────────────────────────────────────

  Widget _buildNavBar(BuildContext context, ReportDraft draft) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          if (_step > 0)
            OutlinedButton.icon(
              key: const Key('wizard_nav_back'),
              onPressed: () => setState(() => _step--),
              icon: const Icon(Icons.chevron_left),
              label: const Text('Back'),
            )
          else
            const SizedBox.shrink(),

          if (_step == 0 && draft.charts.isNotEmpty)
            Text(
              '${draft.charts.length} chart${draft.charts.length == 1 ? '' : 's'} added',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.primary,
                  ),
            ),

          if (_step < _kStepLabels.length - 1)
            FilledButton.icon(
              key: const Key('wizard_nav_next'),
              onPressed: () => setState(() => _step++),
              icon: const Icon(Icons.chevron_right),
              label: const Text('Next'),
              iconAlignment: IconAlignment.end,
            )
          else
            FilledButton(
              key: const Key('wizard_done_button'),
              onPressed: () {
                ref.read(builderProvider.notifier).reset();
                ref.read(selectedReportProvider.notifier).select(null);
              },
              child: const Text('Done'),
            ),
        ],
      ),
    );
  }

  // ── Save ──────────────────────────────────────────────────────────────────

  Future<void> _save(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _saving = true);
    try {
      await ref
          .read(builderProvider.notifier)
          .save(widget.caseId, widget.reportId);
      if (!mounted) return;
      messenger.showSnackBar(
        const SnackBar(content: Text('Report saved.')),
      );
    } on NsightApiException catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(
        SnackBar(content: Text('Save failed: ${e.detail}')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

// ---------------------------------------------------------------------------
// Step chip widget
// ---------------------------------------------------------------------------

class _StepChip extends StatelessWidget {
  const _StepChip({
    required this.step,
    required this.label,
    required this.isActive,
    required this.isCompleted,
  });

  final int step;
  final String label;
  final bool isActive;
  final bool isCompleted;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final primary = theme.colorScheme.primary;
    final onSurface = theme.colorScheme.onSurface;

    final circleColor = isActive || isCompleted
        ? primary.withValues(alpha: isCompleted ? 0.6 : 1.0)
        : null;
    final circleBorder = isActive || isCompleted
        ? null
        : Border.all(
            color: onSurface.withValues(alpha: 0.38),
            width: 1.5,
          );

    final labelColor = isActive
        ? primary
        : isCompleted
            ? onSurface.withValues(alpha: 0.8)
            : onSurface.withValues(alpha: 0.5);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: circleColor,
            border: circleBorder,
          ),
          child: Center(
            child: isCompleted
                ? Icon(
                    Icons.check,
                    size: 16,
                    color: theme.colorScheme.onPrimary,
                  )
                : Text(
                    '$step',
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: isActive
                          ? theme.colorScheme.onPrimary
                          : onSurface.withValues(alpha: 0.38),
                    ),
                  ),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
            color: labelColor,
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Placeholder step (steps 3–5)
// ---------------------------------------------------------------------------

class _PlaceholderStep extends StatelessWidget {
  const _PlaceholderStep();

  @override
  Widget build(BuildContext context) {
    final onSurface = Theme.of(context).colorScheme.onSurface;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.construction,
            size: 48,
            color: onSurface.withValues(alpha: 0.38),
          ),
          const SizedBox(height: 16),
          Text(
            'Coming soon',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: onSurface.withValues(alpha: 0.6),
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'This step will be implemented in a follow-up task.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: onSurface.withValues(alpha: 0.5),
                ),
          ),
        ],
      ),
    );
  }
}
