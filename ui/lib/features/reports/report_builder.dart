// Two-panel report builder: question pick-list (left) + chart cards (right).
// REQ-C-10 / REQ-C-11 / REQ-C-13 / REQ-C-14 / REQ-C-15 / REQ-C-26
// REQ-U-06 / REQ-U-11.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/services/nsight_api.dart';
import 'chart_spec_editor.dart';
import 'providers/builder_provider.dart';
import 'providers/reports_provider.dart';
import 'question_pick_list.dart';
import 'report_preview.dart';

/// Breakpoint below which the two panels are stacked vertically.
const _kNarrowBreakpoint = 700.0;

/// Two-panel report builder.
///
/// Left panel: [QuestionPickList] — searchable checkboxes; "Add checked →"
///   appends chart cards. (REQ-C-11 / REQ-U-11)
/// Right panel: [ReorderableListView] of [ChartSpecEditor] cards. (REQ-C-14/15)
///
/// Top bar: editable name, Save, Render/Build toggle, and a back button that
/// returns to the [ReportsList]. Reports are always rendered as images (W4). (REQ-U-06)
class ReportBuilder extends ConsumerStatefulWidget {
  const ReportBuilder({
    super.key,
    required this.caseId,
    required this.reportId,
  });

  final String caseId;
  final String reportId;

  @override
  ConsumerState<ReportBuilder> createState() => _ReportBuilderState();
}

class _ReportBuilderState extends ConsumerState<ReportBuilder> {
  final _nameController = TextEditingController();
  bool _nameInitialized = false;
  bool _saving = false;
  /// When true, the Preview panel (REportPreview) is shown instead of the
  /// question/chart-card panels. (REQ-C-19a / REQ-C-21)
  bool _showPreview = false;

  @override
  void initState() {
    super.initState();
    // Schedule load after the first frame so ProviderScope is ready.
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

    // Initialise the name controller once when the draft first loads.
    if (draft != null && !_nameInitialized) {
      _nameController.text = draft.name;
      _nameInitialized = true;
    }

    if (draft == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final isNarrow =
        MediaQuery.of(context).size.width < _kNarrowBreakpoint;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildTopBar(context, draft),
        const Divider(height: 1),
        Expanded(
          child: _showPreview
              ? ReportPreview(
                  caseId: widget.caseId,
                  reportId: widget.reportId,
                )
              : (isNarrow
                  ? _buildNarrowBody(context, draft)
                  : _buildWideBody(context, draft)),
        ),
      ],
    );
  }

  // ── Top bar ───────────────────────────────────────────────────────────────

  Widget _buildTopBar(BuildContext context, ReportDraft draft) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Wrap(
        alignment: WrapAlignment.start,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 8,
        runSpacing: 8,
        children: [
          // Back button — clears the builder draft before returning to the
          // reports list so opening another report starts with a fresh state.
          // (FIX-2)
          IconButton(
            key: const Key('back_button'),
            icon: const Icon(Icons.arrow_back),
            tooltip: 'Back to reports list',
            onPressed: () {
              ref.read(builderProvider.notifier).reset();
              ref.read(selectedReportProvider.notifier).select(null);
            },
          ),

          // Editable name
          SizedBox(
            width: 240,
            child: TextField(
              key: const Key('report_name_field'),
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

          // Save (REQ-C-10)
          ElevatedButton.icon(
            key: const Key('save_button'),
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

          // Render / Build toggle — shows/hides the preview panel. (REQ-C-21)
          ElevatedButton.icon(
            key: const Key('render_button'),
            onPressed: () => setState(() => _showPreview = !_showPreview),
            icon: Icon(
              _showPreview ? Icons.edit : Icons.play_arrow,
            ),
            label: Text(_showPreview ? 'Build' : 'Render'),
          ),
        ],
      ),
    );
  }

  // ── Body layouts ──────────────────────────────────────────────────────────

  Widget _buildWideBody(BuildContext context, ReportDraft draft) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Left: question pick-list (fixed width)
        SizedBox(
          width: 320,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                child: Text(
                  'Questions',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              const Expanded(child: QuestionPickList()),
            ],
          ),
        ),
        const VerticalDivider(width: 1),
        // Right: chart cards
        Expanded(child: _buildChartCards(context, draft)),
      ],
    );
  }

  Widget _buildNarrowBody(BuildContext context, ReportDraft draft) {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          const TabBar(
            tabs: [Tab(text: 'Questions'), Tab(text: 'Charts')],
          ),
          Expanded(
            child: TabBarView(
              children: [
                const QuestionPickList(),
                _buildChartCards(context, draft),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChartCards(BuildContext context, ReportDraft draft) {
    final charts = draft.charts;
    if (charts.isEmpty) {
      return const Center(
        child: Text('No charts yet. Add questions from the left panel.'),
      );
    }

    return ReorderableListView.builder(
      padding: const EdgeInsets.only(bottom: 16),
      onReorder: (oldIndex, newIndex) {
        ref.read(builderProvider.notifier).reorder(oldIndex, newIndex);
      },
      itemCount: charts.length,
      itemBuilder: (context, index) {
        return ChartSpecEditor(
          key: ValueKey('chart_card_$index'),
          index: index,
          spec: charts[index],
          renderMode: draft.renderMode,
        );
      },
    );
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  Future<void> _save(BuildContext context) async {
    // Cache messenger before the async gap to avoid context-after-await lint.
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
