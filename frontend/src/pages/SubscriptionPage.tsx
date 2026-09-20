import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
import {
  subscriptionService,
  type SubscriptionResponse,
  type SubscriptionTier,
} from '@/services/subscription.service';
import Card from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import toast from 'react-hot-toast';
import { CheckIcon } from '@heroicons/react/24/outline';
import { getErrorMessage } from '@/utils/errors';
import { formatMoney, formatNumber } from '@/i18n';
import { useT } from '@/i18n/react';

/**
 * The reader's subscription, and what the other tiers offer.
 *
 * ── THE PRICE WAS ENGLISH WITH A DOLLAR SIGN WELDED ON ──────────────────────────────────────
 *
 * `` `$${price.toFixed(2)}` `` wrote "$9.99" for every reader in every language. French writes
 * "9,99 $" — symbol after the figure, comma for the decimal, a no-break space between them —
 * and the currency was assumed to be dollars rather than read from the `currency` the payload
 * carries. `formatMoney` in src/i18n does both. English output is unchanged.
 *
 * ── WHAT IS THE BACKEND'S AND STAYS THE BACKEND'S ───────────────────────────────────────────
 *
 * A tier's name, its description, the market names it lists, the subscription status and the
 * message a successful tier change returns are all rendered exactly as the server sent them, in
 * both languages. Translating a server's own message would be putting words in its mouth, and
 * the market names are the ones the rest of the site shows. The billing period is the one
 * exception, and a narrow one: `perPeriod` is a `select` over the backend's own word, so a
 * period it does not recognise falls through to that word rather than vanishing.
 *
 * ── THE COUNTS AGREE NOW ────────────────────────────────────────────────────────────────────
 *
 * "1 predictions/day" and "1 days history" were wrong in English as well as untranslatable; both
 * sentences state their own plural branches now, in each language's own rule.
 */
const SubscriptionPage: React.FC = () => {
  const t = useT();
  const [currentSubscription, setCurrentSubscription] = useState<SubscriptionResponse | null>(null);
  const [availableTiers, setAvailableTiers] = useState<SubscriptionTier[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUpgrading, setIsUpgrading] = useState(false);
  const [selectedTier, setSelectedTier] = useState<string | null>(null);

  useEffect(() => {
    const loadSubscriptionData = async () => {
      try {
        setIsLoading(true);
        const [subscription, tiers] = await Promise.all([
          subscriptionService.getCurrentSubscription(),
          subscriptionService.getSubscriptionTiers(),
        ]);
        setCurrentSubscription(subscription);
        setAvailableTiers(tiers);
      } catch (error) {
        console.error('Failed to load subscription data:', error);
        toast.error(t('auth.subscription.loadFailed'));
      } finally {
        setIsLoading(false);
      }
    };

    loadSubscriptionData();
    // Loaded once. `t` is only here for the failure toast and must not re-fetch because the
    // reader changed language.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleUpgrade = async (newTier: string) => {
    if (newTier === currentSubscription?.tier) {
      toast.error(t('auth.subscription.alreadyOnTier'));
      return;
    }

    try {
      setIsUpgrading(true);
      setSelectedTier(newTier);
      const response = await subscriptionService.updateSubscription({
        new_tier: newTier as 'free' | 'basic' | 'premium' | 'pro',
      });
      setCurrentSubscription(response.subscription);
      // The server's own sentence, in the server's own words. Not ours to translate.
      toast.success(response.message);
    } catch (error) {
      console.error('Failed to update subscription:', error);
      const errorMessage = getErrorMessage(error, t('auth.subscription.updateFailed'));
      toast.error(errorMessage);
    } finally {
      setIsUpgrading(false);
      setSelectedTier(null);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center text-secondary-400">{t('auth.subscription.loading')}</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <Helmet>
        <title>{t('auth.subscription.documentTitle')}</title>
        <meta name="description" content={t('auth.subscription.documentDescription')} />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">{t('auth.subscription.heading')}</h1>
            <p className="text-secondary-400">{t('auth.subscription.subheading')}</p>
          </div>

          {/* Current Subscription */}
          {currentSubscription && (
            <Card className="p-6 mb-8">
              <h2 className="text-xl font-semibold text-white mb-4">{t('auth.subscription.current')}</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-secondary-400">{t('auth.subscription.plan')}</p>
                  <p className="text-lg font-semibold text-white capitalize">
                    {currentSubscription.tier_name}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-secondary-400">{t('auth.subscription.status')}</p>
                  <Badge variant={currentSubscription.status === 'active' ? 'success' : 'warning'}>
                    {currentSubscription.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-secondary-400">{t('auth.subscription.price')}</p>
                  <p className="text-lg font-semibold text-white" data-testid="subscription-price">
                    {formatMoney(currentSubscription.price, currentSubscription.currency)}
                    {t('auth.subscription.perPeriod', { period: currentSubscription.billing_period })}
                  </p>
                </div>
              </div>

              {currentSubscription.usage && (
                <div className="mt-6 pt-6 border-t border-dark-700">
                  <h3 className="text-lg font-semibold text-white mb-3">{t('auth.subscription.usageHeading')}</h3>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-secondary-400">{t('auth.subscription.predictionsUsed')}</span>
                        <span className="text-white">
                          {formatNumber(currentSubscription.usage.predictions_today)} /{' '}
                          {currentSubscription.usage.predictions_limit
                            ? formatNumber(currentSubscription.usage.predictions_limit)
                            : t('auth.subscription.unlimited')}
                        </span>
                      </div>
                      {currentSubscription.usage.predictions_limit && (
                        <div
                          className="w-full bg-dark-700 rounded-full h-2"
                          role="progressbar"
                          aria-label={t('auth.subscription.predictionsUsed')}
                          aria-valuemin={0}
                          aria-valuemax={currentSubscription.usage.predictions_limit}
                          aria-valuenow={currentSubscription.usage.predictions_today}
                        >
                          <div
                            className="bg-primary-600 h-2 rounded-full"
                            style={{
                              width: `${
                                (currentSubscription.usage.predictions_today /
                                  currentSubscription.usage.predictions_limit) *
                                100
                              }%`,
                            }}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* Available Plans */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {availableTiers.map((tier) => (
              <Card
                key={tier.tier}
                className={`p-6 relative ${
                  tier.is_current ? 'ring-2 ring-primary-600' : ''
                } ${tier.is_popular ? 'ring-2 ring-yellow-500' : ''}`}
              >
                {tier.is_popular && (
                  <div className="absolute top-0 right-0 bg-yellow-500 text-dark-950 px-3 py-1 text-xs font-semibold rounded-bl-lg rounded-tr-lg">
                    {t('auth.subscription.popular')}
                  </div>
                )}
                {tier.is_current && (
                  <div className="absolute top-0 left-0 bg-primary-600 text-white px-3 py-1 text-xs font-semibold rounded-tl-lg rounded-br-lg">
                    {t('auth.subscription.currentBadge')}
                  </div>
                )}

                <div className="mt-4">
                  {/* The tier's name and its description are the backend's own words. */}
                  <h3 className="text-xl font-bold text-white capitalize">{tier.name}</h3>
                  <p className="text-sm text-secondary-400 mt-1">{tier.description}</p>
                  <div className="mt-4">
                    <span className="text-3xl font-bold text-white">{formatMoney(tier.price, tier.currency)}</span>
                    <span className="text-secondary-400">
                      {t('auth.subscription.perPeriod', { period: tier.billing_period })}
                    </span>
                  </div>
                </div>

                <div className="mt-6 space-y-3">
                  <div className="flex items-start gap-2">
                    <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-secondary-300">
                      {tier.features.daily_predictions
                        ? t('auth.subscription.predictionsPerDay', { count: tier.features.daily_predictions })
                        : t('auth.subscription.predictionsPerDayUnlimited')}
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-secondary-300">
                      {/* Market names as the rest of the site shows them, joined, not reworded. */}
                      {t('auth.subscription.markets', { markets: tier.features.markets.join(', ') })}
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-secondary-300">
                      {tier.features.history_days
                        ? t('auth.subscription.historyDays', { count: tier.features.history_days })
                        : t('auth.subscription.historyUnlimited')}
                    </span>
                  </div>
                  {tier.features.confidence_visible && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">{t('auth.subscription.confidence')}</span>
                    </div>
                  )}
                  {tier.features.expert_predictions && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">{t('auth.subscription.expertPredictions')}</span>
                    </div>
                  )}
                  {tier.features.advanced_analytics && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">{t('auth.subscription.advancedAnalytics')}</span>
                    </div>
                  )}
                  {tier.features.api_access && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">{t('auth.subscription.apiAccess')}</span>
                    </div>
                  )}
                </div>

                <button
                  onClick={() => handleUpgrade(tier.tier)}
                  disabled={tier.is_current || (isUpgrading && selectedTier === tier.tier)}
                  className={`w-full mt-6 px-4 py-2 rounded-lg font-medium transition-colors ${
                    tier.is_current
                      ? 'bg-dark-700 text-secondary-400 cursor-not-allowed'
                      : 'bg-primary-600 hover:bg-primary-700 text-white'
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {tier.is_current
                    ? t('auth.subscription.currentPlan')
                    : isUpgrading && selectedTier === tier.tier
                    ? t('auth.subscription.processing')
                    : tier.price > (currentSubscription?.price || 0)
                    ? t('auth.subscription.upgrade')
                    : t('auth.subscription.downgrade')}
                </button>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </>
  );
};

export default SubscriptionPage;

