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

const SubscriptionPage: React.FC = () => {
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
        toast.error('Failed to load subscription information');
      } finally {
        setIsLoading(false);
      }
    };

    loadSubscriptionData();
  }, []);

  const handleUpgrade = async (newTier: string) => {
    if (newTier === currentSubscription?.tier) {
      toast.error('You are already on this tier');
      return;
    }

    try {
      setIsUpgrading(true);
      setSelectedTier(newTier);
      const response = await subscriptionService.updateSubscription({
        new_tier: newTier as 'free' | 'basic' | 'premium' | 'pro',
      });
      setCurrentSubscription(response.subscription);
      toast.success(response.message);
    } catch (error: any) {
      console.error('Failed to update subscription:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to update subscription';
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
          <div className="text-center text-secondary-400">Loading subscription information...</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <Helmet>
        <title>Subscription - Soccer Predictions</title>
        <meta name="description" content="Manage your subscription plan" />
      </Helmet>

      <div className="min-h-screen bg-dark-950 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white">Subscription Management</h1>
            <p className="text-secondary-400">Choose the plan that's right for you</p>
          </div>

          {/* Current Subscription */}
          {currentSubscription && (
            <Card className="p-6 mb-8">
              <h2 className="text-xl font-semibold text-white mb-4">Current Subscription</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <p className="text-sm text-secondary-400">Plan</p>
                  <p className="text-lg font-semibold text-white capitalize">
                    {currentSubscription.tier_name}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-secondary-400">Status</p>
                  <Badge variant={currentSubscription.status === 'active' ? 'success' : 'warning'}>
                    {currentSubscription.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-secondary-400">Price</p>
                  <p className="text-lg font-semibold text-white">
                    ${currentSubscription.price.toFixed(2)}/{currentSubscription.billing_period}
                  </p>
                </div>
              </div>

              {currentSubscription.usage && (
                <div className="mt-6 pt-6 border-t border-dark-700">
                  <h3 className="text-lg font-semibold text-white mb-3">Usage Today</h3>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-secondary-400">Predictions Used</span>
                        <span className="text-white">
                          {currentSubscription.usage.predictions_today} /{' '}
                          {currentSubscription.usage.predictions_limit || 'Unlimited'}
                        </span>
                      </div>
                      {currentSubscription.usage.predictions_limit && (
                        <div className="w-full bg-dark-700 rounded-full h-2">
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
                    POPULAR
                  </div>
                )}
                {tier.is_current && (
                  <div className="absolute top-0 left-0 bg-primary-600 text-white px-3 py-1 text-xs font-semibold rounded-tl-lg rounded-br-lg">
                    CURRENT
                  </div>
                )}

                <div className="mt-4">
                  <h3 className="text-xl font-bold text-white capitalize">{tier.name}</h3>
                  <p className="text-sm text-secondary-400 mt-1">{tier.description}</p>
                  <div className="mt-4">
                    <span className="text-3xl font-bold text-white">${tier.price.toFixed(2)}</span>
                    <span className="text-secondary-400">/{tier.billing_period}</span>
                  </div>
                </div>

                <div className="mt-6 space-y-3">
                  <div className="flex items-start gap-2">
                    <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-secondary-300">
                      {tier.features.daily_predictions || 'Unlimited'} predictions/day
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-secondary-300">
                      {tier.features.markets.join(', ')} markets
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-secondary-300">
                      {tier.features.history_days || 'Unlimited'} days history
                    </span>
                  </div>
                  {tier.features.confidence_visible && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">Confidence levels</span>
                    </div>
                  )}
                  {tier.features.expert_predictions && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">Expert predictions</span>
                    </div>
                  )}
                  {tier.features.advanced_analytics && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">Advanced analytics</span>
                    </div>
                  )}
                  {tier.features.api_access && (
                    <div className="flex items-start gap-2">
                      <CheckIcon className="h-5 w-5 text-primary-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-secondary-300">API access</span>
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
                    ? 'Current Plan'
                    : isUpgrading && selectedTier === tier.tier
                    ? 'Processing...'
                    : tier.price > (currentSubscription?.price || 0)
                    ? 'Upgrade'
                    : 'Downgrade'}
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

