// Riverpod provider for the nSight API client.
// REQ-U-04

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/nsight_api.dart';

/// Provides the singleton [NsightApi] instance.
///
/// Override this in tests or integration environments by passing a
/// [ProviderScope] override with a fake/mock [NsightApi].
final nsightApiProvider = Provider<NsightApi>((ref) => NsightApi());
